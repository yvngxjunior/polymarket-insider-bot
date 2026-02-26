from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from bot.database import get_db, TrackedWallet
from bot.trading.polymarket import PolymarketDataClient
from bot.utils.logger import logger

# Nettoyage du dict _recent_trades toutes les N updates
# pour éviter le leak mémoire sur des milliers de marchés distincts (BUG-3).
_CLEANUP_EVERY = 500


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
    wallet_count: int
    total_amount_usdc: float
    avg_price: float
    wallets: list[str]
    confidence: float

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
    Fenêtre de détection: 10 minutes. Seuil minimum: 2 wallets.

    FIX BUG-3: nettoyage périodique de _recent_trades pour éviter le leak
    mémoire progressif sur des runs longue durée (milliers de marchés distincts).
    FIX M2: confidence calculée correctement — les scores wallet sont déjà
    entre 0 et 1, donc pas de division par 100.
    """

    WINDOW_SECONDS = 600
    MIN_WALLETS = 2

    def __init__(self, client: PolymarketDataClient):
        self.client = client
        self._recent_trades: dict[str, list[dict]] = defaultdict(list)
        self._update_count = 0

    async def process_trade(
        self,
        wallet: str,
        token_id: str,
        condition_id: str,
        side: str,
        amount: float,
        price: float,
        timestamp: float,
    ) -> Optional[ConvergenceSignal]:
        now = timestamp
        cutoff = now - self.WINDOW_SECONDS

        self._recent_trades[token_id].append({
            "wallet": wallet, "amount": amount,
            "price": price, "side": side, "ts": now,
        })
        self._recent_trades[token_id] = [
            t for t in self._recent_trades[token_id] if t["ts"] > cutoff
        ]

        # FIX BUG-3: nettoyage périodique des clés expirées
        self._update_count += 1
        if self._update_count % _CLEANUP_EVERY == 0:
            self._cleanup_stale(cutoff)

        same_side = [
            t for t in self._recent_trades[token_id]
            if t["side"].upper() == side.upper()
        ]
        unique_wallets = list({t["wallet"] for t in same_side})

        if len(unique_wallets) < self.MIN_WALLETS:
            return None

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

    def _cleanup_stale(self, cutoff: float) -> None:
        """Supprime les clés dont tous les trades ont expiré la fenêtre de 10min."""
        stale_keys = [
            k for k, trades in self._recent_trades.items()
            if not trades or all(t["ts"] <= cutoff for t in trades)
        ]
        for k in stale_keys:
            del self._recent_trades[k]
        if stale_keys:
            logger.debug(f"[CONV] Cleaned {len(stale_keys)} stale token_id(s) from memory")

    async def _compute_confidence(self, wallet_addresses: list[str]) -> float:
        """
        FIX M2: wallet.score est entre 0 et 1, PAS entre 0 et 100.
        L'ancienne division par 100 donnait une confidence toujours < 0.01.
        """
        try:
            with get_db() as db:
                wallets = [db.get(TrackedWallet, addr) for addr in wallet_addresses]
                scores = [w.score for w in wallets if w is not None and w.score is not None]
            return sum(scores) / len(scores) if scores else 0.5
        except Exception:
            return 0.5
