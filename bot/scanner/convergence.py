from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from bot.database import get_db, TrackedWallet
from bot.trading.polymarket import PolymarketDataClient
from bot.utils.logger import logger

_CLEANUP_EVERY = 500


@dataclass
class ConvergenceSignal:
    """
    Signal fort: plusieurs wallets insiders ont misé sur le même outcome
    dans une fenêtre de temps courte.
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
            return "ULTRA (5+ insiders)"
        elif self.wallet_count >= 3:
            return "STRONG (3-4 insiders)"
        return "MODERATE (2 insiders)"


class ConvergenceDetector:
    """
    Détecte quand plusieurs wallets insiders s'alignent sur le même outcome.
    Fenêtre de détection: 10 minutes. Seuil minimum: 2 wallets.

    FIX BUG-3:  nettoyage périodique de _recent_trades (anti-leak mémoire).
    FIX M2:     confidence calculée correctement (scores déjà entre 0 et 1).
    FIX CONV-1: normalisation timestamp ms→s.
    FIX CONV-2: guard float(amount or 0) et float(price or 0).
    FIX CONV-4: fenêtre calculée avec datetime.utcnow() (pas timestamp API).
    FIX CONV-5: avg_price et total_amount dédupliqués par wallet (biais multi-trades).
    FIX CONV-6: _compute_confidence log warning si aucun wallet trouvé en DB.
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
        # FIX CONV-1: normalisation ms → s
        if timestamp > 1e12:
            timestamp /= 1000

        # FIX CONV-2: protection contre None
        amount = float(amount or 0)
        price  = float(price or 0)

        # FIX CONV-4: fenêtre basée sur now() réel, pas timestamp API
        now    = datetime.utcnow().timestamp()
        cutoff = now - self.WINDOW_SECONDS

        self._recent_trades[token_id].append({
            "wallet": wallet, "amount": amount,
            "price": price, "side": side, "ts": now,
        })
        self._recent_trades[token_id] = [
            t for t in self._recent_trades[token_id] if t["ts"] > cutoff
        ]

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

        # FIX CONV-5: déduplication par wallet avant calcul avg_price + total_amount
        # Sans dédup, un wallet actif avec 10 trades biaisait fortement la moyenne
        # en lui donnant 10x plus de poids qu'un wallet avec 1 seul trade.
        unique_trades = list({t["wallet"]: t for t in same_side}.values())
        total_amount = sum(t["amount"] for t in unique_trades)
        avg_price = (
            sum(t["price"] for t in unique_trades) / len(unique_trades)
            if unique_trades else 0.0
        )

        confidence = await self._compute_confidence(unique_wallets)
        signal = ConvergenceSignal(
            token_id=token_id,
            condition_id=condition_id,
            side=side,
            wallet_count=len(unique_wallets),
            total_amount_usdc=total_amount,
            avg_price=avg_price,
            wallets=unique_wallets,
            confidence=confidence,
        )
        logger.info(
            f"[CONV] {signal.strength} -- "
            f"{len(unique_wallets)} wallets on {token_id[:16]}... "
            f"${signal.total_amount_usdc:,.0f} USDC | confidence={confidence:.0%}"
        )
        return signal

    def _cleanup_stale(self, cutoff: float) -> None:
        stale_keys = [
            k for k, trades in self._recent_trades.items()
            if not trades or all(t["ts"] <= cutoff for t in trades)
        ]
        for k in stale_keys:
            del self._recent_trades[k]
        if stale_keys:
            logger.debug(f"[CONV] Cleaned {len(stale_keys)} stale token_id(s) from memory")

    async def _compute_confidence(self, wallet_addresses: list[str]) -> float:
        """FIX CONV-6: log warning si aucun wallet trouvé en DB (signal sans base)."""
        try:
            with get_db() as db:
                wallets = [db.get(TrackedWallet, addr) for addr in wallet_addresses]
                scores = [w.score for w in wallets if w is not None and w.score is not None]
            if not scores:
                logger.warning(
                    f"[CONV] _compute_confidence: none of {len(wallet_addresses)} wallet(s) "
                    f"found in DB — defaulting confidence=0.5"
                )
                return 0.5
            return sum(scores) / len(scores)
        except Exception as e:
            logger.debug(f"[CONV] _compute_confidence error: {e}")
            return 0.5
