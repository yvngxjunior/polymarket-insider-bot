"""
Conviction Filter — inspiré de dexorynlabs/polymarket-trading-bot-python

Filtre multi-critères avant exécution d'un trade copié:
  1. Taille minimale du bet source  (conviction de l'insider)
  2. Plage de prix valide           (évite les marchés quasi-résolus)
  3. Score minimal du wallet source (win_rate historique)
  4. Rate-limit par marché          (anti-spam, max N copies/heure)

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
    _DEFAULT_MIN_BET = 50.0
    _DEFAULT_MIN_SCORE = 0.65
    _DEFAULT_MAX_PRICE = 0.92
    _DEFAULT_MIN_PRICE = 0.04
    _MAX_COPIES_PER_HOUR = 3

    def __init__(self) -> None:
        self.min_bet: float = getattr(settings, "min_source_bet_usdc", self._DEFAULT_MIN_BET)
        self.min_score: float = getattr(settings, "min_wallet_score", self._DEFAULT_MIN_SCORE)
        self.max_price: float = settings.max_price
        self.min_price: float = settings.min_price
        # Mémoire légère pour le rate-limit (in-process uniquement)
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
        # Score proportionnel: 1.0 à 500 USDC, plafonné
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
        # Score centré sur 0.50 (marchés les plus incertains = plus de valeur)
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

    # ------------------------------------------------------------------
    # Evaluation globale
    # ------------------------------------------------------------------
    def evaluate(
        self,
        source_amount: float,
        price: float,
        wallet_score: float = 1.0,
        market_id: str = "",
    ) -> FilterResult:
        """
        Évalue tous les filtres en séquence.
        Retourne au premier échec (fast-fail).
        Si tout passe, retourne un FilterResult avec le score moyen pondéré.
        """
        checks: list[FilterResult] = [
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

        # Score global = moyenne pondérée (bet size a plus de poids)
        scores = [c.score for c in checks]
        weights = [0.4, 0.2, 0.3, 0.1] if market_id else [0.4, 0.25, 0.35]
        weights = weights[:len(scores)]
        total_w = sum(weights)
        avg_score = sum(s * w for s, w in zip(scores, weights)) / total_w

        # Enregistre cette copie pour le rate-limit
        if market_id:
            self._market_copies[market_id].append(datetime.utcnow())

        logger.debug(f"[FILTER] ✓ All checks passed — conviction score={avg_score:.2f}")
        return FilterResult(passed=True, reason="All checks passed", score=round(avg_score, 3))
