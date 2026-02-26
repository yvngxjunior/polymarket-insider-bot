from bot.config import get_settings
from bot.database import get_db, TrackedWallet
from bot.trading.polymarket import PolymarketDataClient
from bot.utils.logger import logger

settings = get_settings()


class WhaleTracker:
    """
    Détecte les gros mouvements de capitaux sur Polymarket.
    Un 'whale event' = un trade unique dépassant le seuil configuré.

    La Data API /trades retourne les champs :
      proxyWallet, side, asset, conditionId, size, price, timestamp, title, transactionHash
    get_recent_large_trades() normalise proxyWallet → 'maker' en interne.
    """

    def __init__(self, client: PolymarketDataClient):
        self.client = client
        self._seen_tx: set[str] = set()

    async def scan(self) -> list[dict]:
        """
        Retourne les nouveaux gros trades depuis le dernier scan.
        Chaque élément contient: wallet, montant, marché, side, prix.
        """
        large_trades = await self.client.get_recent_large_trades(
            min_amount=settings.whale_threshold
        )

        new_events = []
        for trade in large_trades:
            tx_id = trade.get("transactionHash", "")
            if not tx_id or tx_id in self._seen_tx:
                continue

            self._seen_tx.add(tx_id)

            wallet = trade.get("maker", "")   # normalisé depuis proxyWallet
            amount = float(trade.get("usdcSize", 0))
            title  = trade.get("title", trade.get("conditionId", "???")[:16])

            logger.info(
                f"🐋 WHALE: {wallet[:10]}... "
                f"${amount:,.0f} USDC | {trade.get('side')} | {title[:45]}"
            )

            # Marque le wallet comme whale en DB s'il existe
            with get_db() as db:
                w = db.get(TrackedWallet, wallet)
                if w:
                    w.is_whale = True

            new_events.append({
                "wallet":       wallet,
                "amount_usdc":  amount,
                "condition_id": trade.get("conditionId", ""),
                "token_id":     trade.get("asset", ""),
                "side":         trade.get("side", "BUY"),
                "price":        float(trade.get("price", 0)),
                "tx_hash":      tx_id,
                "title":        title,
            })

        # Limite la taille du set pour éviter une fuite mémoire
        if len(self._seen_tx) > 10_000:
            self._seen_tx = set(list(self._seen_tx)[-5_000:])

        return new_events
