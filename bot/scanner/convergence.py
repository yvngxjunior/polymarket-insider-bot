import asyncio
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from bot.database import get_db, TrackedWallet
from bot.trading.polymarket import PolymarketDataClient
from bot.utils.logger import logger


@dataclass
class ConvergenceSignal:
    """
    Signal fort: plusieurs wallets insiders ont misé sur le même outcome
    dans une fenêtre de temps courte.
    Plus il y en a, plus le signal est fort.
    """
    token_id: str
    condition_id: str
    side: str
    wallet_count: int          # Nombre de wallets qui convergent
    total_amount_usdc: float   # Volume total engagé
    avg_price: float           # Prix moyen d'entrée
    wallets: list[str]         # Adresses concernées
    confidence: float          # Score 0-1 basé sur la qualité des wallets

    @property
    def strength(self) -> str:
        if self.wallet_count >= 5:
            return "🔥 ULTRA (5+ insiders)"
        elif self.wallet_count >= 3:
            return "⚡ STRONG (3-4 insiders)"
        return "🔵 MODERATE (2 insiders)"


class ConvergenceDetector:
    """
    Detecte quand plusieurs wallets insiders s'alignent sur le même outcome.

    C'est le signal le plus profitable du bot:
    Si 3 wallets Elite (score A) misent la même chose dans un intervalle
    de 10 minutes, la probabilité de gain est très élevée.

    Fenêtre de détection: 10 minutes par défaut.
    Seuil minimum: 2 wallets.
    """

    WINDOW_SECONDS = 600     # 10 minutes
    MIN_WALLETS = 2          # Minimum pour déclencher un signal

    def __init__(self, client: PolymarketDataClient):
        self.client = client
        # token_id -> list of {wallet, amount, price, side, timestamp}
        self._recent_trades: dict[str, list[dict]] = defaultdict(list)

    async def process_trade(
        self,
        wallet: str,
        token_id: str,
        condition_id: str,
        side: str,
        amount: float,
        price: float,
        timestamp: float,  # unix timestamp
    ) -> Optional[ConvergenceSignal]:
        """
        Enregistre un trade et vérifie si d'autres wallets ont fait pareil récemment.
        Retourne un ConvergenceSignal si le seuil est atteint, None sinon.
        """
        now = timestamp
        cutoff = now - self.WINDOW_SECONDS

        # Ajouter ce trade
        self._recent_trades[token_id].append({
            "wallet": wallet,
            "amount": amount,
            "price": price,
            "side": side,
            "ts": now,
        })

        # Nettoyer les trades hors fenêtre
        self._recent_trades[token_id] = [
            t for t in self._recent_trades[token_id]
            if t["ts"] > cutoff
        ]

        # Filtrer par side (on veut des trades dans la même direction)
        same_side = [
            t for t in self._recent_trades[token_id]
            if t["side"].upper() == side.upper()
        ]

        unique_wallets = list({t["wallet"] for t in same_side})

        if len(unique_wallets) < self.MIN_WALLETS:
            return None

        # Récupère les scores des wallets pour calculer la confiance
        confidence = await self._compute_confidence(unique_wallets)

        signal = ConvergenceSignal(
            token_id=token_id,
            condition_id=condition_id,
            side=side,
            wallet_count=len(unique_wallets),
            total_amount_usdc=sum(t["amount"] for t in same_side),
            avg_price=sum(t["price"] for t in same_side) / len(same_side),
            wallets=unique_wallets,
            confidence=confidence,
        )

        logger.info(
            f"🔥 CONVERGENCE SIGNAL: {signal.strength} — "
            f"{len(unique_wallets)} wallets on {token_id[:16]}... "
            f"${signal.total_amount_usdc:,.0f} USDC | confidence={confidence:.0%}"
        )
        return signal

    async def _compute_confidence(self, wallet_addresses: list[str]) -> float:
        """
        Calcule la confiance du signal selon la qualité des wallets convergents.
        Confidence = moyenne des scores normalisés (0-1).
        """
        try:
            with get_db() as db:
                wallets = [
                    db.get(TrackedWallet, addr)
                    for addr in wallet_addresses
                ]
                scores = [
                    w.score / 100.0 for w in wallets if w is not None
                ]
            return sum(scores) / len(scores) if scores else 0.5
        except Exception:
            return 0.5
