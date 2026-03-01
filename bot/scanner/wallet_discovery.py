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
    min_win_rate: float = 0.60  # 60% minimum (will calculate from pnl/vol)
    min_volume_usd: float = 5000.0  # $5k minimum volume
    min_pnl_usd: float = 500.0  # $500 minimum profit
    
    # Leaderboard settings (Updated to v1 API)
    leaderboard_url: str = "https://data-api.polymarket.com/v1/leaderboard"
    fetch_limit: int = 50  # Max 50 per request (API limit)
    
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
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict]:
        """
        Fetch traders from Polymarket leaderboard.
        
        Args:
            period: "DAY", "WEEK", "MONTH", "ALL"
            order_by: "PNL" or "VOL"
            limit: Number of traders to fetch (max 50)
            offset: Pagination offset
            
        Returns:
            List of trader dicts with stats
        """
        session = await self._get_session()
        
        for attempt in range(self.config.max_retries):
            try:
                params = {
                    "period": period,
                    "orderBy": order_by,
                    "limit": min(limit, 50),  # API max is 50
                    "offset": offset,
                    "category": "OVERALL",
                }
                
                async with session.get(
                    self.config.leaderboard_url,
                    params=params,
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        # API returns array directly
                        traders = data if isinstance(data, list) else []
                            
                        logger.info(
                            f"[DISCOVERY] Fetched {len(traders)} traders from leaderboard "
                            f"(offset={offset})"
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
        
        API Response fields:
        - proxyWallet: Address
        - vol: Volume in USDC
        - pnl: Profit/loss in USDC
        - rank: Leaderboard position
        
        Filters:
        - PnL >= min_pnl_usd
        - Volume >= min_volume_usd
        - Not already tracked
        
        Returns:
            List of qualified wallets with computed score
        """
        with get_db() as db:
            existing = {w.address.lower() for w in db.query(TrackedWallet).all()}
            
        qualified = []
        
        for trader in traders:
            # API field: proxyWallet
            address = trader.get("proxyWallet", "")
            if not address or address.lower() in existing:
                continue
                
            # Extract stats from API
            pnl = trader.get("pnl", 0.0)
            volume = trader.get("vol", 0.0)
            rank = trader.get("rank", 999)
            username = trader.get("userName", "Unknown")
            
            # Calculate win rate estimate from pnl/volume
            # If PnL is positive and significant, assume good WR
            estimated_win_rate = 0.5 + (pnl / max(volume, 1)) * 0.5
            estimated_win_rate = max(0.0, min(estimated_win_rate, 1.0))
            
            # Apply filters
            if (
                pnl >= self.config.min_pnl_usd
                and volume >= self.config.min_volume_usd
                and estimated_win_rate >= self.config.min_win_rate
            ):
                score = self._calculate_score(estimated_win_rate, volume, pnl)
                qualified.append({
                    "address": address,
                    "win_rate": estimated_win_rate,
                    "volume_usd": volume,
                    "pnl": pnl,
                    "rank": rank,
                    "username": username,
                    "score": score,
                    "source": "leaderboard_discovery",
                })
                
        # Sort by score descending
        qualified.sort(key=lambda x: x["score"], reverse=True)
        
        logger.info(
            f"[DISCOVERY] Filtered {len(qualified)}/{len(traders)} qualified wallets"
        )
        
        return qualified
        
    def _calculate_score(self, win_rate: float, volume: float, pnl: float) -> float:
        """
        Calculate composite quality score.
        
        Formula:
        - Win rate (estimated): 40% weight
        - Volume (log scale): 30% weight
        - PnL: 30% weight
        
        Returns:
            Score between 0.0 and 1.0
        """
        import math
        
        # Win rate component (0.0 - 0.4)
        wr_component = win_rate * 0.4
        
        # Volume component (0.0 - 0.3)
        volume_normalized = math.log10(max(volume, 1)) / 5.0
        volume_component = min(volume_normalized, 1.0) * 0.3
        
        # PnL component (0.0 - 0.3)
        # Normalize: $5k = 0.5, $50k = 1.0
        pnl_normalized = math.log10(max(pnl, 1)) / 4.7  # log10(50000) ≈ 4.7
        pnl_component = min(pnl_normalized, 1.0) * 0.3
        
        total_score = wr_component + volume_component + pnl_component
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
                        label=f"@{wallet_data.get('username', 'Unknown')} (Rank #{wallet_data.get('rank', '?')})",
                        win_rate=wallet_data["win_rate"],
                        total_trades=0,  # Not provided by API
                        total_profit_usd=wallet_data["pnl"],
                        score=wallet_data["score"],
                        is_active=True,
                        is_whale=wallet_data["volume_usd"] > 50000,
                        first_seen=datetime.utcnow(),
                        last_activity=datetime.utcnow(),
                    )
                    db.add(wallet)
                    added_count += 1
                    
                    logger.info(
                        f"[DISCOVERY] ✅ Added {wallet_data['address'][:10]}... | "
                        f"@{wallet_data.get('username', 'Unknown')} | "
                        f"PnL=${wallet_data['pnl']:.0f} | Score={wallet_data['score']:.2f}"
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
        fetch_pages: int = 2,  # Fetch 2 pages = 100 traders
    ) -> Dict[str, int]:
        """
        Run complete discovery cycle.
        
        Args:
            period: Leaderboard period to query (DAY, WEEK, MONTH, ALL)
            auto_add: If True, automatically add qualified wallets to DB
            fetch_pages: Number of pages to fetch (50 traders per page)
            
        Returns:
            Stats dict with counts
        """
        logger.info(f"[DISCOVERY] Starting discovery cycle (period={period})...")
        
        # Fetch multiple pages
        all_traders = []
        for page in range(fetch_pages):
            offset = page * 50
            traders = await self.fetch_leaderboard(
                period=period,
                limit=50,
                offset=offset,
            )
            if not traders:
                break
            all_traders.extend(traders)
            await asyncio.sleep(self.config.rate_limit_delay)  # Rate limit
        
        if not all_traders:
            logger.warning("[DISCOVERY] No traders fetched")
            return {"fetched": 0, "qualified": 0, "added": 0}
            
        # Filter qualified
        qualified = self.filter_quality_wallets(all_traders)
        
        # Add to DB if enabled
        added = 0
        if auto_add and qualified:
            added = await self.add_wallets_to_db(qualified)
            
        logger.info(
            f"✅ [DISCOVERY] Complete | Fetched={len(all_traders)} | "
            f"Qualified={len(qualified)} | Added={added}"
        )
        
        return {
            "fetched": len(all_traders),
            "qualified": len(qualified),
            "added": added,
        }


async def discover_wallets(
    min_pnl_usd: float = 500.0,
    min_volume_usd: float = 5000.0,
) -> Dict[str, int]:
    """
    Convenience function to run wallet discovery.
    
    Args:
        min_pnl_usd: Minimum profit filter
        min_volume_usd: Minimum volume filter
        
    Returns:
        Discovery stats
    """
    config = WalletDiscoveryConfig()
    config.min_pnl_usd = min_pnl_usd
    config.min_volume_usd = min_volume_usd
    
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
