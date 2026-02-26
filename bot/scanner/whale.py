from bot.config import get_settings
from bot.database import get_db, TrackedWallet
from bot.trading.polymarket import PolymarketDataClient
from bot.utils.logger import logger

settings = get_settings()


class WhaleTracker:
    """
    Détecte les gros mouvements de capitaux sur Polymarket.

    Stratégie de déduplication :
      1. Si transactionHash présent  → clé = transactionHash
      2. Sinon                        → clé = proxyWallet + '|' + conditionId + '|' + str(timestamp)
    Ainsi un trade sans hash n'est jamais re-notifié deux fois.
    """

    def __init__(self, client: PolymarketDataClient):
        self.client = client
        self._seen: set[str] = set()

    @staticmethod
    def _dedup_key(trade: dict) -> str:
        tx = trade.get("transactionHash", "").strip()
        if tx:
            return tx
        # Fallback : wallet + marché + timestamp (arrondi à la minute pour absorber
        # les petites variations d'arrondi entre appels)
        ts_min = int(trade.get("timestamp", 0)) // 60
        return f"{trade.get('maker', '')}|{trade.get('conditionId', '')}|{ts_min}"

    async def scan(self) -> list[dict]:
        large_trades = await self.client.get_recent_large_trades(
            min_amount=settings.whale_threshold
        )

        # Log brut à la première réponse non vide pour aider au debug
        if large_trades:
            sample = large_trades[0]
            logger.debug(
                f"[WHALE raw] keys={list(sample.keys())} "
                f"tx={sample.get('transactionHash','<empty>')} "
                f"title={sample.get('title','')[:40]}"
            )

        new_events = []
        for trade in large_trades:
            key = self._dedup_key(trade)
            if key in self._seen:
                continue
            self._seen.add(key)

            wallet = trade.get("maker", "")
            amount = float(trade.get("usdcSize", 0))
            title  = trade.get("title", "") or trade.get("conditionId", "???")[:20]

            logger.info(
                f"🐋 WHALE: {wallet[:10]}... "
                f"${amount:,.0f} USDC | {trade.get('side')} | {title[:45]}"
            )

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
                "tx_hash":      key,
                "title":        title,
            })

        if len(self._seen) > 10_000:
            self._seen = set(list(self._seen)[-5_000:])

        return new_events
