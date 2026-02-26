"""
Position Sizer — Kelly fractionnaire + Tiered Multipliers.

Formule Kelly: f* = (p * (b+1) - 1) / b
  où p = win_rate estimé, b = (1-price)/price
  On applique kelly_fraction_sizer (défaut 0.25 = Quarter-Kelly) pour limiter la variance.

FIX BUG-8: PositionSizer._capital est désormais synchronisé avec
  RiskManager.portfolio.total_capital avant chaque calcul via sync_capital().

FIX SIZER-1: TIERED_MULTIPLIERS configurable via .env.
FIX ZERO-HARDCODE: KELLY_FRACTION et MIN_TRADE_USDC lus depuis settings.
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
    max_usd: float          # float('inf') pour la dernière tranche
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
    Format: "min-max:mult,min-max:mult,min+:mult"
    Retourne [] si raw est vide ou invalide → fallback sans tiered.
    """
    if not raw or not raw.strip():
        return []
    bands: list[TieredBand] = []
    try:
        for part in raw.strip().split(","):
            part = part.strip()
            if not part:
                continue
            range_str, mult_str = part.split(":")
            mult = float(mult_str)
            range_str = range_str.strip()
            if range_str.endswith("+"):
                min_v = float(range_str[:-1])
                max_v = float("inf")
            else:
                lo, hi = range_str.split("-")
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
    KELLY_FRACTION_SIZER et MIN_TRADE_USDC configurables dans .env.
    """

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
                f"[SIZER] Tiered multipliers OFF — pure Kelly "
                f"(KELLY_FRACTION_SIZER={settings.kelly_fraction_sizer}, "
                f"MIN_TRADE_USDC={settings.min_trade_usdc}) "
                "| /setcapital pour activer"
            )

    def update_capital(self, capital_usdc: float) -> None:
        if capital_usdc > 0:
            self._capital = capital_usdc

    def sync_capital(self, risk_manager) -> None:
        """Synchronise le capital depuis RiskManager.portfolio.total_capital."""
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
        if not (0.01 <= yes_price <= 0.99):
            return SizeResult(
                amount_usdc=settings.min_trade_usdc,
                pct_of_capital=0.0,
                kelly_fraction=0.0,
                rationale=f"Invalid price {yes_price:.3f}",
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
