"""
Conviction Filter

Filtre multi-critères avant exécution d'un trade copié:
  1. Taille minimale du bet source  (conviction de l'insider)
  2. Plage de prix valide           (évite les marchés quasi-résolus)
  3. Score minimal du wallet source (win_rate historique)
  4. Rate-limit par marché          (anti-spam, max N copies/heure)
  5. Losing streak protection ✔️    (skip si wallet en série de pertes)
  6. Score de timing d'entrée ✔️ NEW (skip si wallet entre trop tard)

Tous les seuils sont configurables via .env.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from bot.config import get_settings
from bot.utils.logger import logger

settings = get_settings()


@dataclass
class FilterResult:
    passed: bool
    reason: str
    score: float = 1.0    # 0.0-1.0 — utilisé pour le Kelly sizing en aval


class ConvictionFilter:
    """
    Applique une série de filtres rapides (synchrones) avant de déclencher
    la logique de risque et d'exécution, plus coûteuse.
    """

    # Seuils par défaut (overridés par settings si définis)
    _DEFAULT_MIN_BET   = 50.0
    _DEFAULT_MIN_SCORE = 0.65
    _DEFAULT_MAX_PRICE = 0.92
    _DEFAULT_MIN_PRICE = 0.04
    _MAX_COPIES_PER_HOUR = 3

    # Losing streak: skip si X pertes consécutives ou plus
    MAX_CONSECUTIVE_LOSSES = 3

    # Timing: skip si l'insider entre à un prix déjà trop élevé
    # (signe qu'il est en retard sur l'information)
    MAX_ENTRY_PRICE_TIMING = 0.70
    MIN_TIMING_SCORE       = 0.30   # score de timing en dessous duquel on skip

    def __init__(self) -> None:
        self.min_bet: float   = getattr(settings, "min_source_bet_usdc", self._DEFAULT_MIN_BET)
        self.min_score: float = getattr(settings, "min_wallet_score", self._DEFAULT_MIN_SCORE)
        self.max_price: float = settings.max_price
        self.min_price: float = settings.min_price
        self._market_copies: dict[str, list[datetime]] = defaultdict(list)

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
        """
        Skip un wallet dont les N derniers trades connus sont des pertes.
        0-2 pertes : léger malus de score.
        3+  pertes : SKIP complèt.
        """
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
        """
        Filtre de timing d'entrée.

        Un wallet qui entre à un prix > 0.70 est probablement en retard
        sur l'information : l'alpha a déjà été capturé par d'autres.

        Deux conditions indépendantes pour le reject:
          A. Le prix actuel est > MAX_ENTRY_PRICE_TIMING (0.70)
          B. Le score de timing du wallet est < MIN_TIMING_SCORE (0.30)
             (wallets qui entrent systématiquement tard)

        Si le prix est élevé MAIS que le wallet a un bon timing score
        (>= MIN_TIMING_SCORE), on laisse passer avec un malus.
        """
        price_late    = price > self.MAX_ENTRY_PRICE_TIMING
        timing_poor   = entry_timing_score < self.MIN_TIMING_SCORE

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
            # Prix haut mais wallet avec bon timing historique → malus modéré
            penalty = (price - self.MAX_ENTRY_PRICE_TIMING) * 2.0
            adjusted = max(0.1, entry_timing_score - penalty)
            logger.debug(
                f"[FILTER] Late entry price={price:.2f} but good timing "
                f"score={entry_timing_score:.2f} → adjusted={adjusted:.2f}"
            )
            return FilterResult(passed=True, reason="ok", score=adjusted)

        # Prix normal → le score de timing booste ou maluse légèrement
        score = max(0.1, entry_timing_score)
        return FilterResult(passed=True, reason="ok", score=score)

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
        """
        Évalue tous les filtres en séquence (fast-fail au premier échec).

        Args:
            source_amount:       Montant USDC misé par l'insider
            price:               Prix du token (0.0 – 1.0)
            wallet_score:        Win rate pondéré du wallet (0.0 – 1.0)
            market_id:           ID marché Polymarket (pour rate-limit)
            consecutive_losses:  Nombre de pertes consécutives récentes
            entry_timing_score:  Score de timing du wallet (depuis InsiderScanner)
                                 0.0 = entre toujours tard | 1.0 = entre toujours tôt

        Returns:
            FilterResult(passed, reason, score)
        """
        checks: list[FilterResult] = [
            self._check_losing_streak(consecutive_losses),   # en premier — le plus rapide
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

        # Score global = moyenne pondérée
        scores = [c.score for c in checks]
        if market_id:
            weights = [0.10, 0.20, 0.25, 0.15, 0.20, 0.10]
        else:
            weights = [0.10, 0.20, 0.30, 0.15, 0.25]
        weights = weights[:len(scores)]
        total_w = sum(weights)
        avg_score = sum(s * w for s, w in zip(scores, weights)) / total_w

        if market_id:
            self._market_copies[market_id].append(datetime.utcnow())

        logger.debug(f"[FILTER] ✓ All checks passed — conviction score={avg_score:.2f}")
        return FilterResult(passed=True, reason="All checks passed", score=round(avg_score, 3))
