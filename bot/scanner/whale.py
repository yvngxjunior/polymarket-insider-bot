from bot.config import get_settings
from bot.database import get_db, TrackedWallet
from bot.trading.polymarket import PolymarketDataClient
from bot.utils.logger import logger

settings = get_settings()

# FIX: seuil de résolution — au-delà le marché est quasi-résolu, les
# alertes whale sont du bruit (rachats de tokens à valeur faciale, pas de signal).
RESOLVING_HIGH = 0.95   # prix YES > 0.95 → marché considéré résolu YES
RESOLVING_LOW  = 0.05   # prix YES < 0.05 → marché considéré résolu NO


class WhaleTracker:
    """
    Détecte les gros mouvements de capitaux sur Polymarket.

    Stratégie de déduplication :
      1. Si transactionHash présent  → clé = transactionHash
      2. Sinon                        → clé = proxyWallet + '|' + conditionId + '|' + str(timestamp)
    Ainsi un trade sans hash n'est jamais re-notifié deux fois.

    FIX: filtre les marchés quasi-résolus (price >0.95 ou <0.05).
    Ces trades sont des rachats de tokens à valeur quasi-faciale — pas des signaux
    d'insiders. Ils génèrent du spam Telegram et faussent le score des wallets.
    FIX: filtre aussi les SELL — seuls les BUY sont des signaux d'entrée.
    """

    def __init__(self, client: PolymarketDataClient):
        self.client = client
        self._seen: set[str] = set()

    @staticmethod
    def _dedup_key(trade: dict) -> str:
        tx = trade.get("transactionHash", "").strip()
        if tx:
            return tx
        ts_min = int(trade.get("timestamp", 0)) // 60
        return f"{trade.get('maker', '')}|{trade.get('conditionId', '')}|{ts_min}"

    @staticmethod
    def _is_market_resolved(price: float) -> bool:
        """Retourne True si le marché est quasi-résolu (pas de signal utile)."""
        return price >= RESOLVING_HIGH or price <= RESOLVING_LOW

    async def scan(self) -> list[dict]:
        large_trades = await self.client.get_recent_large_trades(
            min_amount=settings.whale_threshold
        )

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

            price  = float(trade.get("price", 0))
            side   = trade.get("side", "BUY").upper()
            wallet = trade.get("maker", "")
            amount = float(trade.get("usdcSize", 0))
            title  = trade.get("title", "") or trade.get("conditionId", "???")[:20]

            # FIX: ignore les marchés résolus — pas de signal, spam pur
            if self._is_market_resolved(price):
                logger.debug(
                    f"[WHALE skip] Resolved market @ {price:.3f} — {title[:45]}"
                )
                continue

            # FIX: ignore les SELL — ce sont des sorties de position, pas des entrées
            if side == "SELL":
                logger.debug(
                    f"[WHALE skip] SELL ignored — {wallet[:10]}... ${amount:,.0f} on {title[:35]}"
                )
                continue

            logger.info(
                f"🐋 WHALE: {wallet[:10]}... "
                f"${amount:,.0f} USDC | {side} @ {price:.3f} | {title[:45]}"
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
                "side":         side,
                "price":        price,
                "tx_hash":      key,
                "title":        title,
            })

        if len(self._seen) > 10_000:
            self._seen = set(list(self._seen)[-5_000:])

        return new_events
