"""
Wallet Scorer — PolyInsider Bot
================================
Calcule le score composite d'un wallet insider sur 4 dimensions (A/B/C/D)
pour décider si on doit le tracker et combien de conviction lui accorder.

Dimensions:
  A. Win rate pondéré (corrigé par le volume de trades)
  B. Précision récente (30 derniers jours vs historique global)
  C. Taille des bets (whales ont plus de conviction = signal plus fort)
  D. Consistance (faible variance des résultats = wallet fiable)

Formule finale:
  score = 0.40*A + 0.30*B + 0.20*C + 0.10*D   (tout ramené entre 0.0 et 1.0)

Tier system:
  ELITE  score ≥ 0.80  → on copie tout, max conviction
  STRONG score ≥ 0.65  → on copie avec conviction normale
  WEAK   score ≥ 0.50  → on copie seulement les gros bets
  SKIP   score <  0.50  → on ignore ce wallet
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class WalletTier(str, Enum):
    ELITE  = "ELITE"    # score >= 0.80
    STRONG = "STRONG"   # score >= 0.65
    WEAK   = "WEAK"     # score >= 0.50
    SKIP   = "SKIP"     # score <  0.50


@dataclass
class WalletScore:
    """Résultat du scoring d'un wallet."""
    address: str
    score: float            # score composite 0.0 – 1.0
    tier: WalletTier
    score_a: float          # win rate pondéré
    score_b: float          # précision récente
    score_c: float          # taille des bets
    score_d: float          # consistance
    should_track: bool      # True si tier != SKIP

    def __str__(self) -> str:
        return (
            f"[{self.tier.value}] {self.address[:10]}... "
            f"score={self.score:.2f} "
            f"(A={self.score_a:.2f} B={self.score_b:.2f} "
            f"C={self.score_c:.2f} D={self.score_d:.2f})"
        )


class WalletScorer:
    """
    Calcule le score composite d'un wallet.

    Args:
        elite_threshold:  seuil score pour tier ELITE  (défaut 0.80)
        strong_threshold: seuil score pour tier STRONG (défaut 0.65)
        weak_threshold:   seuil score pour tier WEAK   (défaut 0.50)
        whale_threshold:  taille de bet considérée "whale" en USDC (défaut 500)
    """

    WEIGHTS = {"A": 0.40, "B": 0.30, "C": 0.20, "D": 0.10}

    def __init__(
        self,
        elite_threshold: float = 0.80,
        strong_threshold: float = 0.65,
        weak_threshold: float = 0.50,
        whale_threshold: float = 500.0,
    ) -> None:
        self.elite_threshold  = elite_threshold
        self.strong_threshold = strong_threshold
        self.weak_threshold   = weak_threshold
        self.whale_threshold  = whale_threshold

    # ------------------------------------------------------------------
    # Point d'entrée principal
    # ------------------------------------------------------------------

    def score_wallet(
        self,
        address: str,
        win_rate: float,
        total_trades: int,
        recent_win_rate: float,
        avg_bet_usdc: float,
        pnl_stddev: float = 0.0,
    ) -> WalletScore:
        """
        Calcule le score composite d'un wallet.

        Args:
            address:         adresse du wallet
            win_rate:        taux de victoire historique global (0.0-1.0)
            total_trades:    nombre total de trades (pour pondération)
            recent_win_rate: win rate sur les 30 derniers jours (0.0-1.0)
            avg_bet_usdc:    taille moyenne des bets en USDC
            pnl_stddev:      écart-type des P&L (0 = parfaitement consistant)

        Returns:
            WalletScore avec score composite, tier et détail des dimensions
        """
        a = self._score_a(win_rate, total_trades)
        b = self._score_b(recent_win_rate, win_rate)
        c = self._score_c(avg_bet_usdc)
        d = self._score_d(pnl_stddev, avg_bet_usdc)

        composite = (
            self.WEIGHTS["A"] * a
            + self.WEIGHTS["B"] * b
            + self.WEIGHTS["C"] * c
            + self.WEIGHTS["D"] * d
        )
        composite = round(min(max(composite, 0.0), 1.0), 4)
        tier = self._tier(composite)

        return WalletScore(
            address=address,
            score=composite,
            tier=tier,
            score_a=round(a, 4),
            score_b=round(b, 4),
            score_c=round(c, 4),
            score_d=round(d, 4),
            should_track=(tier != WalletTier.SKIP),
        )

    # ------------------------------------------------------------------
    # Dimensions individuelles
    # ------------------------------------------------------------------

    def _score_a(self, win_rate: float, total_trades: int) -> float:
        """
        A — Win rate pondéré par le volume de trades.
        Poche moins de 15 trades → score réduit (bruit statistique).
        """
        if total_trades <= 0:
            return 0.0
        # Facteur de confiance: log-linéaire jusqu'à 50 trades
        confidence = min(math.log1p(total_trades) / math.log1p(50), 1.0)
        return win_rate * confidence

    def _score_b(self, recent_win_rate: float, global_win_rate: float) -> float:
        """
        B — Précision récente vs historique global.
        Si le wallet améliore ses perfs récemment, bonus.
        Si dégradation, malus.
        """
        if global_win_rate <= 0:
            return recent_win_rate
        ratio = recent_win_rate / global_win_rate
        # Normaliser: 1.0 = stable, >1 = en hausse, <1 = en baisse
        return min(recent_win_rate * ratio, 1.0)

    def _score_c(self, avg_bet_usdc: float) -> float:
        """
        C — Taille des bets (signal de conviction insider).
        Score log-normalisé entre 0 et 1:
          $10   → ~0.10
          $100  → ~0.40
          $500  → ~0.75  (seuil whale)
          $2000 → ~1.00
        """
        if avg_bet_usdc <= 0:
            return 0.0
        return min(math.log1p(avg_bet_usdc) / math.log1p(2000), 1.0)

    def _score_d(self, pnl_stddev: float, avg_bet_usdc: float) -> float:
        """
        D — Consistance (coefficient de variation inversé).
        Un wallet qui gagne régulièrement vaut mieux qu'un wallet chanceux.
        stddev=0 → score=1.0 (parfaitement consistant)
        """
        if avg_bet_usdc <= 0 or pnl_stddev < 0:
            return 1.0
        cv = pnl_stddev / avg_bet_usdc  # coefficient de variation
        return max(1.0 - min(cv / 2.0, 1.0), 0.0)

    # ------------------------------------------------------------------
    # Tier
    # ------------------------------------------------------------------

    def _tier(self, score: float) -> WalletTier:
        if score >= self.elite_threshold:
            return WalletTier.ELITE
        if score >= self.strong_threshold:
            return WalletTier.STRONG
        if score >= self.weak_threshold:
            return WalletTier.WEAK
        return WalletTier.SKIP
