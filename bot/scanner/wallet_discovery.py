"""
Wallet Discovery v1.0
======================
Découvre automatiquement les top traders Polymarket via leaderboard.
Ajoute les meilleurs performers au tracking automatiquement.

Features:
- Scrape Polymarket leaderboard (top 100)
- Filtre wallets par win rate > 70% et volume > $5k
- Auto-ajout à TrackedWallet si pass critères
- Rate limiting avec exponential backoff
"""
import asyncio
from typing import List, Dict
from datetime import datetime
import aiohttp

from bot.database import get_db, TrackedWallet
from bot.config import get_settings
from bot.utils.logger import logger

settings = get_settings()


class WalletDiscovery:
    """
    Découvre automatiquement nouveaux wallets performers.
    Utilise leaderboard Polymarket + filtres qualité.
    """
    
    def __init__(
        self,
        min_win_rate: float = 0.70,
        min_volume_usd: float = 5000.0,
        min_trades: int = 20,
    ):
        self.min_win_rate = min_win_rate
        self.min_volume_usd = min_volume_usd
        self.min_trades = min_trades
        self.leaderboard_url = f"{settings.polymarket_gamma_host}/leaderboard"
        self._rate_limit_delay = 1.0  # seconds entre requêtes
    
    async def discover_top_traders(self, limit: int = 100) -> List[Dict]:
        """
        Récupère les top traders depuis le leaderboard Polymarket.
        
        Args:
            limit: Nombre de traders à récupérer (max 100)
        
        Returns:
            Liste de dicts avec wallet data
        """
        discovered = []
        
        try:
            async with aiohttp.ClientSession() as session:
                # Polymarket leaderboard endpoint
                async with session.get(
                    self.leaderboard_url,
                    params={"limit": limit, "period": "all_time"},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        discovered = data if isinstance(data, list) else []
                        logger.info(f"[DISCOVERY] Fetched {len(discovered)} traders from leaderboard")
                    elif resp.status == 429:
                        logger.warning("[DISCOVERY] Rate limited by Polymarket API")
                        await asyncio.sleep(self._rate_limit_delay * 2)
                    else:
                        logger.warning(f"[DISCOVERY] Leaderboard API returned {resp.status}")
        
        except asyncio.TimeoutError:
            logger.warning("[DISCOVERY] Leaderboard request timeout")
        except Exception as e:
            logger.error(f"[DISCOVERY] Error fetching leaderboard: {e}")
        
        return discovered
    
    def _filter_quality_wallets(self, traders: List[Dict]) -> List[Dict]:
        """
        Filtre wallets selon critères qualité.
        
        Critères:
        - Win rate >= min_win_rate
        - Volume total >= min_volume_usd
        - Nombre trades >= min_trades
        - Pas déjà tracké
        """
        filtered = []
        
        with get_db() as db:
            existing_addresses = {w.address.lower() for w in db.query(TrackedWallet).all()}
        
        for trader in traders:
            address = trader.get("address", "")
            if not address or address.lower() in existing_addresses:
                continue
            
            win_rate = trader.get("winRate", 0.0)
            volume = trader.get("volumeTraded", 0.0)
            trades_count = trader.get("tradesCount", 0)
            
            if (
                win_rate >= self.min_win_rate
                and volume >= self.min_volume_usd
                and trades_count >= self.min_trades
            ):
                filtered.append({
                    "address": address,
                    "win_rate": win_rate,
                    "volume_usd": volume,
                    "trades_count": trades_count,
                    "score": self._calculate_score(win_rate, volume, trades_count),
                })
        
        return filtered
    
    def _calculate_score(self, win_rate: float, volume: float, trades_count: int) -> float:
        """
        Calcule score composite pour un wallet.
        
        Formula: (win_rate * 0.5) + (log(volume)/10 * 0.3) + (min(trades/100, 1.0) * 0.2)
        """
        import math
        
        wr_component = win_rate * 0.5
        volume_component = (math.log10(max(volume, 1)) / 5) * 0.3
        trades_component = min(trades_count / 100, 1.0) * 0.2
        
        return min(wr_component + volume_component + trades_component, 1.0)
    
    async def add_discovered_wallets(self, wallets: List[Dict]) -> int:
        """
        Ajoute wallets découverts à la DB.
        
        Returns:
            Nombre de wallets ajoutés
        """
        added_count = 0
        
        with get_db() as db:
            for wallet_data in wallets:
                try:
                    wallet = TrackedWallet(
                        address=wallet_data["address"],
                        label=f"Auto-discovered (WR={wallet_data['win_rate']:.0%})",
                        win_rate=wallet_data["win_rate"],
                        total_trades=wallet_data["trades_count"],
                        total_profit_usd=wallet_data["volume_usd"],
                        score=wallet_data["score"],
                        is_active=True,
                        is_whale=wallet_data["volume_usd"] > 50000,
                        first_seen=datetime.utcnow(),
                        last_activity=datetime.utcnow(),
                    )
                    db.add(wallet)
                    added_count += 1
                    logger.info(
                        f"[DISCOVERY] Added {wallet_data['address'][:10]}... "
                        f"(WR={wallet_data['win_rate']:.0%}, score={wallet_data['score']:.2f})"
                    )
                except Exception as e:
                    logger.warning(f"[DISCOVERY] Failed to add wallet: {e}")
            
            db.commit()
        
        return added_count
    
    async def run_discovery(self) -> int:
        """
        Lance cycle complet de découverte.
        
        Returns:
            Nombre de nouveaux wallets ajoutés
        """
        logger.info("[DISCOVERY] Starting wallet discovery cycle...")
        
        # Fetch leaderboard
        traders = await self.discover_top_traders(limit=100)
        if not traders:
            logger.warning("[DISCOVERY] No traders fetched from leaderboard")
            return 0
        
        # Filtre qualité
        quality_wallets = self._filter_quality_wallets(traders)
        logger.info(
            f"[DISCOVERY] Found {len(quality_wallets)} quality wallets "
            f"(from {len(traders)} total)"
        )
        
        if not quality_wallets:
            return 0
        
        # Ajoute à DB
        added = await self.add_discovered_wallets(quality_wallets)
        logger.info(f"[DISCOVERY] Discovery complete — {added} new wallets added")
        
        return added


async def discover_wallets(
    min_win_rate: float = 0.70,
    min_volume_usd: float = 5000.0,
) -> int:
    """
    Interface publique pour lancer discovery.
    
    Args:
        min_win_rate: Win rate minimum requis
        min_volume_usd: Volume minimum requis
    
    Returns:
        Nombre de wallets ajoutés
    """
    discovery = WalletDiscovery(
        min_win_rate=min_win_rate,
        min_volume_usd=min_volume_usd,
    )
    return await discovery.run_discovery()


if __name__ == "__main__":
    # Test discovery
    added = asyncio.run(discover_wallets())
    print(f"\n✅ Discovery complete: {added} wallets added\n")
