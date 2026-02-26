"""
Position Sizer — Kelly fractionnaire + Tiered Multipliers.

Formule Kelly: f* = (p * (b+1) - 1) / b
  où p = win_rate estimé, b = (1-price)/price
  On applique kelly_fraction_sizer (défaut 0.25 = Quarter-Kelly) pour limiter la variance.

FIX BUG-8:   PositionSizer._capital synchronisé avec RiskManager.portfolio.total_capital
             avant chaque calcul via sync_capital().
FIX SIZER-1: TIERED_MULTIPLIERS configurable via .env.
FIX SIZER-2: _parse_tiered_multipliers guard ValueError sur format invalide.
FIX SIZER-3: calculate() guard conviction_score <= 0 → fallback min_trade_usdc.
FIX ZERO-HARDCODE: toutes les constantes lues depuis settings.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from bot.config import get_settings
from bot.utils.logger import logger

settings = get_settings()

_DEFAULT_CAPITAL = settings.initial_capital


@dataclass
class TieredBand:
    min_usd: float
    max_usd: float
    multiplier: float


@dataclass
class SizeResult:
    amount_usdc: float
    pct_of_capital: float
    kelly_fraction: float
    rationale: str


def _parse_tiered_multipliers(raw: str) -> list[TieredBand]:
    """
    Parse la chaîne TIERED_MULTIPLIERS depuis .env.
    Format: "min-max:mult,min+:mult"
    Retourne [] si raw est vide ou invalide.

    FIX SIZER-2: guard explicite sur split ':' manquant → ValueError propre
    avec message clair au lieu de crash silencieux.
    """
    if not raw or not raw.strip():
        return []
    bands: list[TieredBand] = []
    try:
        for part in raw.strip().split(","):
            part = part.strip()
            if not part:
                continue
            # FIX SIZER-2: valider le format avant split
            if ":" not in part:
                raise ValueError(
                    f"Missing ':' separator in band '{part}' — "
                    f"expected format 'min-max:mult' or 'min+:mult'"
                )
            range_str, mult_str = part.split(":", 1)
            mult = float(mult_str)
            range_str = range_str.strip()
            if range_str.endswith("+"):
                min_v = float(range_str[:-1])
                max_v = float("inf")
            else:
                if "-" not in range_str:
                    raise ValueError(
                        f"Missing '-' in range '{range_str}' — "
                        f"expected 'min-max' format"
                    )
                lo, hi = range_str.split("-", 1)
                min_v = float(lo)
                max_v = float(hi)
            bands.append(TieredBand(min_usd=min_v, max_usd=max_v, multiplier=mult))
    except Exception as e:
        logger.warning(f"[SIZER] TIERED_MULTIPLIERS parse error: {e} — disabling tiered")
        return []
    bands.sort(key=lambda b: b.min_usd)
    return bands


def _get_tiered_multiplier(
    bands: list[TieredBand],
    source_amount: float,
) -> Optional[float]:
    """Retourne le multiplicateur correspondant à source_amount, ou None si aucun band."""
    if not bands:
        return None
    for band in bands:
        if band.min_usd <= source_amount < band.max_usd:
            return band.multiplier
    return bands[-1].multiplier


class PositionSizer:
    """
    Toutes les constantes lues depuis settings (zéro hardcode).
    Configurables dans .env:
      KELLY_FRACTION_SIZER  (défaut: 0.25)
      MIN_TRADE_USDC        (défaut: 2.0)
      MAX_TRADE_AMOUNT      (défaut: 50.0)
      TIERED_MULTIPLIERS    (défaut: vide = Kelly pur)
    """

    @property
    def MIN_TRADE_USDC(self) -> float:
        return settings.min_trade_usdc

    @property
    def KELLY_FRACTION(self) -> float:
        return settings.kelly_fraction_sizer

    def __init__(self, capital_usdc: float = 0.0) -> None:
        self._capital = capital_usdc if capital_usdc > 0 else _DEFAULT_CAPITAL
        raw_tiered = getattr(settings, "tiered_multipliers", "") or ""
        self._tiered_bands: list[TieredBand] = _parse_tiered_multipliers(raw_tiered)
        if self._tiered_bands:
            bands_str = ", ".join(
                f"${b.min_usd:.0f}-"
                + ("∞" if b.max_usd == float("inf") else f"${b.max_usd:.0f}")
                + f":×{b.multiplier}"
                for b in self._tiered_bands
            )
            logger.info(f"[SIZER] Tiered multipliers active: {bands_str}")
        else:
            logger.info(
                f"[SIZER] Pure Kelly — KELLY_FRACTION_SIZER={settings.kelly_fraction_sizer} "
                f"MIN_TRADE_USDC={settings.min_trade_usdc}"
            )

    def update_capital(self, capital_usdc: float) -> None:
        if capital_usdc > 0:
            self._capital = capital_usdc

    def sync_capital(self, risk_manager) -> None:
        """FIX BUG-8: Synchronise le capital depuis RiskManager.portfolio.total_capital."""
        try:
            cap = risk_manager.portfolio.total_capital
            if cap > 0:
                self._capital = cap
        except Exception:
            pass

    def calculate(
        self,
        yes_price: float,
        conviction_score: float,
        source_amount: float = 0.0,
    ) -> SizeResult:
        # FIX SIZER-3: conviction_score invalide → fallback min_trade_usdc
        if conviction_score <= 0:
            logger.debug(
                f"[SIZER] conviction_score={conviction_score:.3f} <= 0 "
                f"— fallback to min_trade_usdc"
            )
            return SizeResult(
                amount_usdc=settings.min_trade_usdc,
                pct_of_capital=0.0,
                kelly_fraction=0.0,
                rationale=f"conviction_score={conviction_score:.3f} invalide → min",
            )

        if not (0.01 <= yes_price <= 0.99):
            return SizeResult(
                amount_usdc=settings.min_trade_usdc,
                pct_of_capital=0.0,
                kelly_fraction=0.0,
                rationale=f"Invalid price {yes_price:.3f} → min ${settings.min_trade_usdc}",
            )

        p = max(0.01, min(0.99, conviction_score))
        b = (1.0 - yes_price) / yes_price

        full_kelly = (p * (b + 1) - 1) / b if b > 0 else 0.0
        fraction = max(0.0, full_kelly * settings.kelly_fraction_sizer)
        fraction = min(fraction, settings.max_position_pct)

        kelly_amount = self._capital * fraction

        tiered_note = ""
        if source_amount > 0 and self._tiered_bands:
            mult = _get_tiered_multiplier(self._tiered_bands, source_amount)
            if mult is not None:
                kelly_amount *= mult
                tiered_note = f" tiered×{mult}"

        final_amount = max(
            settings.min_trade_usdc,
            min(kelly_amount, settings.max_trade_amount),
        )
        final_amount = round(final_amount, 2)
        pct = final_amount / self._capital if self._capital > 0 else 0.0

        if source_amount > 0:
            ratio = final_amount / source_amount
            rationale = (
                f"Kelly({conviction_score:.0%}) p={p:.2f} b={b:.2f}{tiered_note} → "
                f"${final_amount:.2f} (ratio {ratio:.2f}x source ${source_amount:.0f}) "
                f"capital=${self._capital:.0f}"
            )
        else:
            rationale = (
                f"Kelly({conviction_score:.0%}) p={p:.2f} b={b:.2f} → "
                f"${final_amount:.2f} ({pct:.1%} capital=${self._capital:.0f})"
            )

        logger.debug(f"[SIZER] {rationale}")
        return SizeResult(
            amount_usdc=final_amount,
            pct_of_capital=round(pct, 4),
            kelly_fraction=round(fraction, 4),
            rationale=rationale,
        )
