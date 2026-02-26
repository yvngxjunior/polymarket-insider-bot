from bot.config import get_settings
from bot.database import get_db, TrackedWallet
from bot.trading.polymarket import PolymarketDataClient
from bot.utils.logger import logger

settings = get_settings()

RESOLVING_HIGH = 0.95
RESOLVING_LOW  = 0.05


class WhaleTracker:
    """
    Détecte les gros mouvements de capitaux sur Polymarket.

    Filtres actifs:
      1. Déduplication par transactionHash (ou wallet+market+timestamp)
      2. Marchés quasi-résolus (price >0.95 ou <0.05) → skippés
      3. SELL → skippés (sorties de position, pas des signaux d'entrée)
      4. Mots-clés bruit (sports, crypto daily, etc.) → skippés
         Configurable via WHALE_KEYWORDS_BLACKLIST dans .env
    """

    def __init__(self, client: PolymarketDataClient):
        self.client = client
        self._seen: set[str] = set()
        # Cache des mots-clés (immutables pour la durée de vie du process)
        self._noise_keywords: list[str] = settings.get_whale_keywords_blacklist()
        if self._noise_keywords:
            logger.info(
                f"[WHALE] Keyword filter active: {len(self._noise_keywords)} keywords"
            )
        else:
            logger.info("[WHALE] Keyword filter disabled (WHALE_KEYWORDS_BLACKLIST=__none__)")

    @staticmethod
    def _dedup_key(trade: dict) -> str:
        tx = trade.get("transactionHash", "").strip()
        if tx:
            return tx
        ts_min = int(trade.get("timestamp", 0)) // 60
        return f"{trade.get('maker', '')}|{trade.get('conditionId', '')}|{ts_min}"

    @staticmethod
    def _is_market_resolved(price: float) -> bool:
        return price >= RESOLVING_HIGH or price <= RESOLVING_LOW

    def _is_noise_market(self, title: str) -> bool:
        """Retourne True si le titre contient un mot-clé de la blacklist."""
        if not self._noise_keywords:
            return False
        t = title.lower()
        return any(kw in t for kw in self._noise_keywords)

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

            # Filtre 1 — marché quasi-résolu
            if self._is_market_resolved(price):
                logger.debug(f"[WHALE skip/resolved] @ {price:.3f} — {title[:50]}")
                continue

            # Filtre 2 — SELL (sortie de position)
            if side == "SELL":
                logger.debug(f"[WHALE skip/sell] {wallet[:10]}... ${amount:,.0f} — {title[:40]}")
                continue

            # Filtre 3 — marché bruit (sports, crypto daily, etc.)
            if self._is_noise_market(title):
                logger.debug(f"[WHALE skip/noise] {title[:60]}")
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
