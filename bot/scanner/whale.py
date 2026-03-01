from collections import deque
from datetime import datetime
from bot.config import get_settings
from bot.database import get_db, TrackedWallet
from bot.trading.polymarket import PolymarketDataClient
from bot.utils.logger import logger

settings = get_settings()

RESOLVING_HIGH = 0.95
RESOLVING_LOW  = 0.05

# FIX WHALE-1: taille max du cache de deduplication
_SEEN_MAXLEN = 10_000


def _safe_float(value, default: float = 0.0) -> float:
    """
    FIX WHALE-3: conversion float robuste.
    Evite TypeError si l'API retourne null sur price / usdcSize.
    """
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class WhaleTracker:
    """
    Detecte les gros mouvements de capitaux sur Polymarket.

    Filtres actifs:
      1. Deduplication par transactionHash (ou wallet+market+timestamp)
      2. Marches quasi-resolus (price >0.95 ou <0.05) -> skipes
      3. SELL -> skipes (sorties de position, pas des signaux d'entree)
      4. Mots-cles bruit (sports, crypto daily, etc.) -> skipes
         Configurable via WHALE_KEYWORDS_BLACKLIST dans .env

    FIX WHALE-1 -- self._seen remplace le set[str] par deque(maxlen=10_000).
      L'ancienne troncature set(list(self._seen)[-5_000:]) etait non deterministe
      (les sets Python sont non ordonnes -> l'ordre de list(set) est arbitraire
      -> on conservait 5000 cles ALEATOIRES, pas les plus recentes).
      deque(maxlen) expulse automatiquement les entrees les plus anciennes (FIFO)
      sans troncature manuelle. __contains__ reste O(1) via le set interne.

    FIX WHALE-2 -- is_whale mis a jour en batch a la fin du scan
      au lieu d'une transaction DB par trade individuel.
      
    FIX WHALE-4 -- Auto-add whale wallets to tracking
      Les wallets détectés sont automatiquement ajoutés à la DB s'ils n'existent pas.
    """

    def __init__(self, client: PolymarketDataClient):
        self.client = client
        # FIX WHALE-1: deque FIFO avec eviction automatique des plus anciens
        # On utilise un set parallele pour les lookups O(1)
        self._seen_deque: deque[str] = deque(maxlen=_SEEN_MAXLEN)
        self._seen_set: set[str] = set()
        # Cache des mots-cles (immutables pour la duree de vie du process)
        self._noise_keywords: list[str] = settings.get_whale_keywords_blacklist()
        if self._noise_keywords:
            logger.info(
                f"[WHALE] Keyword filter active: {len(self._noise_keywords)} keywords"
            )
        else:
            logger.info("[WHALE] Keyword filter disabled (WHALE_KEYWORDS_BLACKLIST=__none__)")

    def _seen_add(self, key: str) -> None:
        """Ajoute une cle au cache FIFO. Expulse la plus ancienne si maxlen atteint."""
        if len(self._seen_deque) == _SEEN_MAXLEN:
            # La deque va expulser l'element le plus ancien -> on le retire du set aussi
            oldest = self._seen_deque[0]
            self._seen_set.discard(oldest)
        self._seen_deque.append(key)
        self._seen_set.add(key)

    def _seen_contains(self, key: str) -> bool:
        return key in self._seen_set

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
        """Retourne True si le titre contient un mot-cle de la blacklist."""
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
        # FIX WHALE-2: on collecte les wallets whale du cycle
        # pour un seul batch DB a la fin (au lieu d'une connexion par trade)
        whale_wallets_to_flag: list[str] = []
        # FIX WHALE-4: wallets à ajouter automatiquement
        whale_wallets_to_add: dict[str, float] = {}  # {address: amount}

        for trade in large_trades:
            key = self._dedup_key(trade)
            # FIX WHALE-1: lookup O(1) via le set parallele
            if self._seen_contains(key):
                continue
            self._seen_add(key)

            # FIX WHALE-3: _safe_float() protege contre null API
            price  = _safe_float(trade.get("price"))
            amount = _safe_float(trade.get("usdcSize"))
            side   = trade.get("side", "BUY").upper()
            wallet = trade.get("maker", "")
            title  = trade.get("title", "") or trade.get("conditionId", "???")[:20]

            # Filtre 1 — marche quasi-resolu
            if self._is_market_resolved(price):
                logger.debug(f"[WHALE skip/resolved] @ {price:.3f} — {title[:50]}")
                continue

            # Filtre 2 — SELL (sortie de position)
            if side == "SELL":
                logger.debug(f"[WHALE skip/sell] {wallet[:10]}... ${amount:,.0f} — {title[:40]}")
                continue

            # Filtre 3 — marche bruit (sports, crypto daily, etc.)
            if self._is_noise_market(title):
                logger.debug(f"[WHALE skip/noise] {title[:60]}")
                continue

            logger.info(
                f"WHALE: {wallet[:10]}... "
                f"${amount:,.0f} USDC | {side} @ {price:.3f} | {title[:45]}"
            )

            # FIX WHALE-2: accumule les wallets pour le batch update
            # FIX WHALE-4: accumule aussi pour auto-add
            if wallet:
                whale_wallets_to_flag.append(wallet)
                if wallet not in whale_wallets_to_add:
                    whale_wallets_to_add[wallet] = amount

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

        # FIX WHALE-4: Auto-add whale wallets to DB if not tracked
        if whale_wallets_to_add:
            try:
                added_count = 0
                with get_db() as db:
                    for wallet_addr, amount in whale_wallets_to_add.items():
                        wallet_lower = wallet_addr.lower()
                        existing = db.query(TrackedWallet).filter(
                            TrackedWallet.address == wallet_lower
                        ).first()
                        
                        if not existing:
                            # Auto-add avec score conservateur
                            new_wallet = TrackedWallet(
                                address=wallet_lower,
                                label=f"Whale {wallet_addr[:10]}",
                                score=0.70,  # Score initial conservateur
                                total_trades=0,
                                win_rate=0.65,
                                total_profit_usd=amount,
                                is_active=True,
                                is_whale=True,
                                added_at=datetime.utcnow(),
                            )
                            db.add(new_wallet)
                            added_count += 1
                            logger.info(f"[WHALE] ✅ Auto-added {wallet_addr[:10]}... (${amount:,.0f})")
                        else:
                            # Update is_whale flag
                            existing.is_whale = True
                    
                    db.commit()
                    
                if added_count > 0:
                    logger.info(f"[WHALE] Auto-added {added_count} new whale wallet(s) to tracking")
                    
            except Exception as e:
                logger.warning(f"[WHALE] DB auto-add failed: {e}")

        return new_events
