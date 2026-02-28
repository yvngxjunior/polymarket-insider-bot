"""Wallet Discovery v2.0 - Auto-discover top traders from Polymarket leaderboard"""
import asyncio
from typing import List, Dict, Optional
from datetime import datetime
import aiohttp

from bot.database import get_db, TrackedWallet
from bot.config import get_settings
from bot.utils.logger import logger

settings = get_settings()


class WalletDiscoveryConfig:
    """Configuration for wallet discovery"""
    
    # Filtering criteria
    min_win_rate: float = 0.70  # 70% minimum win rate
    min_volume_usd: float = 5000.0  # $5k minimum volume
    min_trades: int = 20  # 20 trades minimum
    
    # Leaderboard settings (Updated Feb 2026)
    leaderboard_url: str = "https://data-api.polymarket.com/leaderboard"
    fetch_limit: int = 100  # Top 100 traders
    
    # Rate limiting
    rate_limit_delay: float = 1.0  # Seconds between requests
    max_retries: int = 3
    

class WalletDiscovery:
    """Auto-discover high-performing wallets from Polymarket"""
    
    def __init__(self, config: Optional[WalletDiscoveryConfig] = None):
        self.config = config or WalletDiscoveryConfig()
        self._session: Optional[aiohttp.ClientSession] = None
        
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={"User-Agent": "PolyInsider-Bot/2.0"},
            )
        return self._session
        
    async def close(self):
        """Close aiohttp session"""
        if self._session and not self._session.closed:
            await self._session.close()
            
    async def fetch_leaderboard(
        self,
        period: str = "ALL",  # DAY, WEEK, MONTH, ALL
        order_by: str = "PNL",  # PNL or VOL
        limit: int = 100,
    ) -> List[Dict]:
        """
        Fetch traders from Polymarket leaderboard.
        
        Args:
            period: "DAY", "WEEK", "MONTH", "ALL"
            order_by: "PNL" or "VOL"
            limit: Number of traders to fetch
            
        Returns:
            List of trader dicts with stats
        """
        session = await self._get_session()
        
        for attempt in range(self.config.max_retries):
            try:
                params = {
                    "period": period,
                    "orderBy": order_by,
                    "limit": limit,
                    "category": "OVERALL",
                }
                
                async with session.get(
                    self.config.leaderboard_url,
                    params=params,
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        # API returns {"leaderboard": [...]} or just [...]
                        traders = data.get("leaderboard", data) if isinstance(data, dict) else data
                        
                        if not isinstance(traders, list):
                            traders = []
                            
                        logger.info(
                            f"[DISCOVERY] Fetched {len(traders)} traders from leaderboard"
                        )
                        return traders
                        
                    elif resp.status == 429:
                        wait_time = self.config.rate_limit_delay * (2 ** attempt)
                        logger.warning(
                            f"[DISCOVERY] Rate limited (429), waiting {wait_time}s..."
                        )
                        await asyncio.sleep(wait_time)
                        
                    else:
                        text = await resp.text()
                        logger.warning(
                            f"[DISCOVERY] API returned {resp.status}: {text[:200]}"
                        )
                        break
                        
            except asyncio.TimeoutError:
                logger.warning(f"[DISCOVERY] Timeout (attempt {attempt + 1}/{self.config.max_retries})")
                await asyncio.sleep(self.config.rate_limit_delay)
                
            except Exception as e:
                logger.error(f"[DISCOVERY] Error fetching leaderboard: {e}")
                break
                
        return []
        
    def filter_quality_wallets(self, traders: List[Dict]) -> List[Dict]:
        """
        Filter traders based on performance criteria.
        
        Filters:
        - Win rate >= min_win_rate
        - Volume >= min_volume_usd
        - Trade count >= min_trades
        - Not already tracked
        
        Returns:
            List of qualified wallets with computed score
        """
        with get_db() as db:
            existing = {w.address.lower() for w in db.query(TrackedWallet).all()}
            
        qualified = []
        
        for trader in traders:
            # API field names (updated for Data API)
            address = trader.get("address", trader.get("user", ""))
            if not address or address.lower() in existing:
                continue
                
            # Extract stats - handle multiple field name variations
            win_rate = trader.get("winRate", trader.get("win_rate", 0.0))
            
            # Volume in USDC
            volume = trader.get("volume", trader.get("volumeTraded", 0.0))
            
            # Trade count
            trades_count = trader.get("trades", trader.get("tradesCount", 0))
            
            # Convert percentages if needed (some APIs return 0-100 instead of 0-1)
            if win_rate > 1.0:
                win_rate = win_rate / 100.0
                
            # Apply filters
            if (
                win_rate >= self.config.min_win_rate
                and volume >= self.config.min_volume_usd
                and trades_count >= self.config.min_trades
            ):
                score = self._calculate_score(win_rate, volume, trades_count)
                qualified.append({
                    "address": address,
                    "win_rate": win_rate,
                    "volume_usd": volume,
                    "trades_count": trades_count,
                    "score": score,
                    "source": "leaderboard_discovery",
                    "pnl": trader.get("pnl", 0.0),
                })
                
        # Sort by score descending
        qualified.sort(key=lambda x: x["score"], reverse=True)
        
        logger.info(
            f"[DISCOVERY] Filtered {len(qualified)}/{len(traders)} qualified wallets"
        )
        
        return qualified
        
    def _calculate_score(self, win_rate: float, volume: float, trades_count: int) -> float:
        """
        Calculate composite quality score.
        
        Formula:
        - Win rate: 50% weight
        - Volume (log scale): 30% weight
        - Trade count (capped at 100): 20% weight
        
        Returns:
            Score between 0.0 and 1.0
        """
        import math
        
        # Win rate component (0.0 - 0.5)
        wr_component = win_rate * 0.5
        
        # Volume component (0.0 - 0.3)
        # log10(5000) = 3.7, log10(100000) = 5.0
        volume_normalized = math.log10(max(volume, 1)) / 5.0
        volume_component = min(volume_normalized, 1.0) * 0.3
        
        # Trade count component (0.0 - 0.2)
        trades_normalized = min(trades_count / 100, 1.0)
        trades_component = trades_normalized * 0.2
        
        total_score = wr_component + volume_component + trades_component
        return min(total_score, 1.0)
        
    async def add_wallets_to_db(self, wallets: List[Dict]) -> int:
        """
        Add discovered wallets to tracked_wallets table.
        
        Returns:
            Number of wallets successfully added
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
                        total_profit_usd=wallet_data.get("pnl", wallet_data["volume_usd"]),
                        score=wallet_data["score"],
                        is_active=True,
                        is_whale=wallet_data["volume_usd"] > 50000,
                        first_seen=datetime.utcnow(),
                        last_activity=datetime.utcnow(),
                    )
                    db.add(wallet)
                    added_count += 1
                    
                    logger.info(
                        f"[DISCOVERY] ➕ Added {wallet_data['address'][:10]}... | "
                        f"WR={wallet_data['win_rate']:.0%} | Score={wallet_data['score']:.2f} | "
                        f"PnL=${wallet_data.get('pnl', 0):.0f}"
                    )
                    
                except Exception as e:
                    logger.warning(
                        f"[DISCOVERY] Failed to add {wallet_data.get('address', 'unknown')}: {e}"
                    )
                    
            db.commit()
            
        return added_count
        
    async def run_discovery(
        self,
        period: str = "ALL",
        auto_add: bool = True,
    ) -> Dict[str, int]:
        """
        Run complete discovery cycle.
        
        Args:
            period: Leaderboard period to query (DAY, WEEK, MONTH, ALL)
            auto_add: If True, automatically add qualified wallets to DB
            
        Returns:
            Stats dict with counts
        """
        logger.info(f"[DISCOVERY] Starting discovery cycle (period={period})...")
        
        # Fetch leaderboard
        traders = await self.fetch_leaderboard(period=period, limit=self.config.fetch_limit)
        
        if not traders:
            logger.warning("[DISCOVERY] No traders fetched")
            return {"fetched": 0, "qualified": 0, "added": 0}
            
        # Filter qualified
        qualified = self.filter_quality_wallets(traders)
        
        # Add to DB if enabled
        added = 0
        if auto_add and qualified:
            added = await self.add_wallets_to_db(qualified)
            
        logger.info(
            f"✅ [DISCOVERY] Complete | Fetched={len(traders)} | "
            f"Qualified={len(qualified)} | Added={added}"
        )
        
        return {
            "fetched": len(traders),
            "qualified": len(qualified),
            "added": added,
        }


async def discover_wallets(
    min_win_rate: float = 0.70,
    min_volume_usd: float = 5000.0,
    min_trades: int = 20,
) -> Dict[str, int]:
    """
    Convenience function to run wallet discovery.
    
    Args:
        min_win_rate: Minimum win rate filter
        min_volume_usd: Minimum volume filter
        min_trades: Minimum trade count filter
        
    Returns:
        Discovery stats
    """
    config = WalletDiscoveryConfig()
    config.min_win_rate = min_win_rate
    config.min_volume_usd = min_volume_usd
    config.min_trades = min_trades
    
    discovery = WalletDiscovery(config)
    
    try:
        stats = await discovery.run_discovery()
        return stats
    finally:
        await discovery.close()


if __name__ == "__main__":
    # Test discovery
    stats = asyncio.run(discover_wallets())
    print(f"\n✅ Discovery complete:")
    print(f"  - Fetched: {stats['fetched']}")
    print(f"  - Qualified: {stats['qualified']}")
    print(f"  - Added: {stats['added']}\n")
