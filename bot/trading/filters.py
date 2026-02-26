"""
Conviction Filter

Filtre multi-critères avant exécution d'un trade copié:
  1. Taille minimale du bet source
  2. Plage de prix valide
  3. Score minimal du wallet source
  4. Rate-limit par marché (anti-spam, max N copies/heure)
  5. Losing streak protection
  6. Score de timing d'entrée

FIX #3        — _market_copies : nettoyage borné toutes les N évaluations.
FIX #5        — Poids de scoring normalisés correctement.
FIX #8        — rate-limit chargé depuis DB au démarrage.
FIX FILTER-1  — status LIKE '%EXECUTED%' (case-insensitive).
FIX FILTER-2  — MAX_CONSECUTIVE_LOSSES lu depuis settings (zéro hardcode).
FIX FILTER-3  — accès direct settings (pas getattr() redondants).
FIX FILTER-4  — enregistrement rate-limit après tous les checks (pas avant).
FIX P2        — _CLEANUP_EVERY 500 → 100 (prévention memory leak).
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from bot.config import get_settings
from bot.utils.logger import logger

settings = get_settings()

# FIX P2: réduit 500 → 100 pour cleanup plus fréquent
# Prévient _market_copies de grossir indéfiniment (memory leak)
_CLEANUP_EVERY = 100


@dataclass
class FilterResult:
    passed: bool
    reason: str
    score: float = 1.0


class ConvictionFilter:

    _DEFAULT_MAX_PRICE = 0.92
    _DEFAULT_MIN_PRICE = 0.04
    _MAX_COPIES_PER_HOUR = 3
    MAX_ENTRY_PRICE_TIMING = 0.70
    MIN_TIMING_SCORE       = 0.30

    def __init__(self) -> None:
        self.min_bet: float   = settings.min_source_bet_usdc
        self.min_score: float = settings.min_wallet_score
        self.max_price: float = settings.max_price
        self.min_price: float = settings.min_price
        self.max_consecutive_losses: int = settings.max_consecutive_losses
        self._market_copies: dict[str, list[datetime]] = defaultdict(list)
        self._eval_count: int = 0
        self._load_rate_limit_from_db()

    def _load_rate_limit_from_db(self) -> None:
        try:
            from bot.database import engine
            from sqlalchemy import text
            cutoff = (datetime.utcnow() - timedelta(hours=1)).isoformat()
            with engine.connect() as conn:
                rows = conn.execute(
                    text(
                        "SELECT market_id, executed_at FROM copied_trades "
                        "WHERE executed_at >= :cutoff AND status LIKE '%EXECUTED%'"
                    ),
                    {"cutoff": cutoff}
                ).fetchall()
            for market_id, executed_at in rows:
                if market_id and executed_at:
                    try:
                        ts = datetime.fromisoformat(str(executed_at))
                        self._market_copies[market_id].append(ts)
                    except Exception:
                        pass
            if rows:
                logger.info(
                    f"[FILTER] Rate-limit loaded from DB: "
                    f"{len(rows)} trades in last 1h across {len(self._market_copies)} markets"
                )
        except Exception as e:
            logger.debug(f"[FILTER] Rate-limit DB load skipped: {e}")

    def _maybe_cleanup(self) -> None:
        self._eval_count += 1
        if self._eval_count % _CLEANUP_EVERY != 0:
            return
        cutoff = datetime.utcnow() - timedelta(hours=1)
        stale_keys = [
            k for k, v in self._market_copies.items()
            if not any(t > cutoff for t in v)
        ]
        for k in stale_keys:
            del self._market_copies[k]
        if stale_keys:
            logger.debug(f"[FILTER] Cleaned {len(stale_keys)} stale rate-limit keys")

    def _check_bet_size(self, source_amount: float) -> FilterResult:
        if source_amount < self.min_bet:
            return FilterResult(
                passed=False,
                reason=f"Source bet ${source_amount:.0f} < min ${self.min_bet:.0f}",
                score=0.0,
            )
        score = min(source_amount / 500.0, 1.0)
        return FilterResult(passed=True, reason="ok", score=score)

    def _check_price(self, price: float) -> FilterResult:
        if price > self.max_price:
            return FilterResult(
                passed=False,
                reason=f"Price {price:.3f} > max {self.max_price} (market likely resolving)",
            )
        if price < self.min_price:
            return FilterResult(
                passed=False,
                reason=f"Price {price:.3f} < min {self.min_price} (too risky)",
            )
        score = 1.0 - abs(price - 0.5) * 1.5
        return FilterResult(passed=True, reason="ok", score=max(0.1, score))

    def _check_wallet_score(self, wallet_score: float) -> FilterResult:
        if wallet_score < self.min_score:
            return FilterResult(
                passed=False,
                reason=f"Wallet score {wallet_score:.0%} < min {self.min_score:.0%}",
                score=0.0,
            )
        return FilterResult(passed=True, reason="ok", score=wallet_score)

    def _check_rate_limit(self, market_id: str) -> FilterResult:
        now = datetime.utcnow()
        cutoff = now - timedelta(hours=1)
        recent = [t for t in self._market_copies[market_id] if t > cutoff]
        self._market_copies[market_id] = recent
        if len(recent) >= self._MAX_COPIES_PER_HOUR:
            return FilterResult(
                passed=False,
                reason=f"Rate limit: {len(recent)}/{self._MAX_COPIES_PER_HOUR} copies on this market in 1h",
            )
        return FilterResult(passed=True, reason="ok", score=1.0)

    def _check_losing_streak(self, consecutive_losses: int) -> FilterResult:
        if consecutive_losses >= self.max_consecutive_losses:
            return FilterResult(
                passed=False,
                reason=(
                    f"Losing streak: {consecutive_losses} consecutive losses — "
                    f"wallet skipped until next win"
                ),
                score=0.0,
            )
        score_penalty = consecutive_losses * 0.10
        return FilterResult(
            passed=True,
            reason="ok",
            score=max(0.1, 1.0 - score_penalty),
        )

    def _check_entry_timing(
        self,
        price: float,
        entry_timing_score: float,
    ) -> FilterResult:
        price_late  = price > self.MAX_ENTRY_PRICE_TIMING
        timing_poor = entry_timing_score < self.MIN_TIMING_SCORE

        if price_late and timing_poor:
            return FilterResult(
                passed=False,
                reason=(
                    f"Late entry: price={price:.2f} > {self.MAX_ENTRY_PRICE_TIMING} "
                    f"AND timing_score={entry_timing_score:.2f} < {self.MIN_TIMING_SCORE}"
                ),
                score=0.0,
            )
        if price_late:
            penalty  = (price - self.MAX_ENTRY_PRICE_TIMING) * 2.0
            adjusted = max(0.1, entry_timing_score - penalty)
            return FilterResult(passed=True, reason="ok", score=adjusted)

        return FilterResult(passed=True, reason="ok", score=max(0.1, entry_timing_score))

    def evaluate(
        self,
        source_amount: float,
        price: float,
        wallet_score: float = 1.0,
        market_id: str = "",
        consecutive_losses: int = 0,
        entry_timing_score: float = 0.5,
    ) -> FilterResult:
        self._maybe_cleanup()

        checks: list[FilterResult] = [
            self._check_losing_streak(consecutive_losses),
            self._check_entry_timing(price, entry_timing_score),
            self._check_bet_size(source_amount),
            self._check_price(price),
            self._check_wallet_score(wallet_score),
        ]
        if market_id:
            checks.append(self._check_rate_limit(market_id))

        for check in checks:
            if not check.passed:
                logger.debug(f"[FILTER] ✗ {check.reason}")
                return check

        BASE_WEIGHTS = {
            0: 0.10,  # losing_streak
            1: 0.20,  # entry_timing
            2: 0.25,  # bet_size
            3: 0.15,  # price
            4: 0.30,  # wallet_score
        }
        RATE_LIMIT_WEIGHT = 0.10

        if market_id:
            scale = 1.0 - RATE_LIMIT_WEIGHT
            weights = [BASE_WEIGHTS[i] * scale for i in range(5)]
            weights.append(RATE_LIMIT_WEIGHT)
        else:
            weights = [BASE_WEIGHTS[i] for i in range(5)]

        total_w   = sum(weights)
        avg_score = sum(c.score * w for c, w in zip(checks, weights)) / total_w

        if market_id:
            self._market_copies[market_id].append(datetime.utcnow())

        logger.debug(f"[FILTER] ✓ All checks passed — conviction score={avg_score:.2f}")
        return FilterResult(passed=True, reason="All checks passed", score=round(avg_score, 3))
