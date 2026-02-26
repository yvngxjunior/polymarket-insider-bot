"""
Conviction Filter

Filtre multi-critères avant exécution d'un trade copié:
  1. Taille minimale du bet source  (conviction de l'insider)
  2. Plage de prix valide           (évite les marchés quasi-résolus)
  3. Score minimal du wallet source (win_rate historique)
  4. Rate-limit par marché          (anti-spam, max N copies/heure)
  5. Losing streak protection       (skip si wallet en série de pertes)
  6. Score de timing d'entrée       (skip si wallet entre trop tard)

Tous les seuils sont configurables via .env.

FIX #3 — _market_copies : nettoyage borné toutes les N évaluations pour
         éviter le leak mémoire sur run longue durée.
FIX #5 — Poids de scoring normalisés correctement quelle que soit
         la présence ou absence de market_id.
FIX #8 — rate-limit chargé depuis DB au démarrage pour survivre
         aux redémarrages du process.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from bot.config import get_settings
from bot.utils.logger import logger

settings = get_settings()

# Nettoyage du cache rate-limit toutes les N évaluations (anti-leak mémoire)
_CLEANUP_EVERY = 500


@dataclass
class FilterResult:
    passed: bool
    reason: str
    score: float = 1.0


class ConvictionFilter:
    """
    Applique une série de filtres rapides (synchrones) avant de déclencher
    la logique de risque et d'exécution.
    """

    _DEFAULT_MIN_BET   = 50.0
    _DEFAULT_MIN_SCORE = 0.65
    _DEFAULT_MAX_PRICE = 0.92
    _DEFAULT_MIN_PRICE = 0.04
    _MAX_COPIES_PER_HOUR = 3

    MAX_CONSECUTIVE_LOSSES = 3
    MAX_ENTRY_PRICE_TIMING = 0.70
    MIN_TIMING_SCORE       = 0.30

    def __init__(self) -> None:
        self.min_bet: float   = getattr(settings, "min_source_bet_usdc", self._DEFAULT_MIN_BET)
        self.min_score: float = getattr(settings, "min_wallet_score", self._DEFAULT_MIN_SCORE)
        self.max_price: float = settings.max_price
        self.min_price: float = settings.min_price
        # FIX #3 — dict borné + compteur de nettoyage
        self._market_copies: dict[str, list[datetime]] = defaultdict(list)
        self._eval_count: int = 0
        # FIX #8 — charge le state du rate-limit depuis la DB au démarrage
        self._load_rate_limit_from_db()

    # ------------------------------------------------------------------
    # FIX #8 — Persistance rate-limit (survie aux redémarrages)
    # ------------------------------------------------------------------

    def _load_rate_limit_from_db(self) -> None:
        """
        Recharge les timestamps de copies récentes (< 1h) depuis copied_trades.
        Ainsi le rate-limit de 3/heure n'est pas bypassable par un restart.
        """
        try:
            from bot.database import engine
            from sqlalchemy import text
            cutoff = (datetime.utcnow() - timedelta(hours=1)).isoformat()
            with engine.connect() as conn:
                rows = conn.execute(
                    text(
                        "SELECT market_id, executed_at FROM copied_trades "
                        "WHERE executed_at >= :cutoff AND status='executed'"
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
        """
        FIX #3 — Purge les entrées expirées toutes les _CLEANUP_EVERY évaluations.
        Borne la mémoire de _market_copies sur runs longue durée.
        """
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

    # ------------------------------------------------------------------
    # Checks individuels
    # ------------------------------------------------------------------

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
        """Empêche de copier le même marché plus de N fois par heure."""
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
        if consecutive_losses >= self.MAX_CONSECUTIVE_LOSSES:
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

    # ------------------------------------------------------------------
    # Évaluation globale
    # ------------------------------------------------------------------

    def evaluate(
        self,
        source_amount: float,
        price: float,
        wallet_score: float = 1.0,
        market_id: str = "",
        consecutive_losses: int = 0,
        entry_timing_score: float = 0.5,
    ) -> FilterResult:
        self._maybe_cleanup()  # FIX #3

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

        # FIX #5 — Score global : moyenne pondérée correctement normalisée
        # Les poids sont définis pour 5 checks de base. Si market_id présent,
        # on ajoute le 6e check avec son propre poids, et on renormalise.
        BASE_WEIGHTS = {
            0: 0.10,  # losing_streak
            1: 0.20,  # entry_timing
            2: 0.25,  # bet_size
            3: 0.15,  # price
            4: 0.30,  # wallet_score
        }
        RATE_LIMIT_WEIGHT = 0.10

        if market_id:
            # Renormalise les 5 poids de base pour faire de la place au 6e
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
