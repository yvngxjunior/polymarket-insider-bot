"""Hot Market Detector - Detects markets with explosive activity.

PHASE 3: Uses complete /activity API to identify markets with:
- Sudden volume spikes (3x+ normal)
- Whale clustering (multiple whales entering)
- Price momentum (rapid price changes)
- High conviction signals (large trades)

Use cases:
1. Early Entry: Copy whales AS SOON AS they enter viral markets
2. Momentum Trading: Ride volume spikes before market resolution
3. Risk Avoidance: Skip markets with suspicious pump patterns

Integration:
- Main loop: Check every 5-10 minutes
- Alerts: Telegram notification when hot market detected
- Auto-copy: Optional fast-track copy (skip normal filters)
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict

from bot.config import get_settings
from bot.database import get_db, TrackedWallet
from bot.trading.polymarket import PolymarketDataClient
from bot.utils.logger import logger

settings = get_settings()


@dataclass
class HotMarketSignal:
    """Hot market detection signal."""
    condition_id: str
    title: str
    signal_type: str  # "WHALE_CLUSTER", "VOLUME_SPIKE", "MOMENTUM"
    strength: str  # "EXTREME", "HIGH", "MEDIUM"
    confidence: float  # 0.0-1.0
    
    # Metrics
    recent_volume_usdc: float
    historical_avg_volume: float
    volume_multiplier: float  # recent / historical
    whale_count: int  # Tracked whales active on this market
    total_traders: int
    
    # Whale details
    whale_addresses: list[str]
    avg_whale_amount: float
    largest_trade_usdc: float
    
    # Price momentum
    current_yes_price: float
    price_change_1h: float  # % change last hour
    
    # Timing
    first_whale_entry: datetime
    detection_timestamp: datetime
    
    def __str__(self) -> str:
        return (
            f"{self.strength} {self.signal_type} | "
            f"{self.title[:50]} | "
            f"Vol: ${self.recent_volume_usdc:,.0f} ({self.volume_multiplier:.1f}x) | "
            f"Whales: {self.whale_count} | "
            f"Conf: {self.confidence:.0%}"
        )


class HotMarketDetector:
    """Detects markets with explosive activity using /activity API.
    
    PHASE 3: Advanced market opportunity detection.
    
    Detection logic:
    1. Get recent activity (last 1-3 hours)
    2. Group by market (condition_id)
    3. Compare recent volume to historical baseline
    4. Identify whale clustering
    5. Calculate momentum score
    6. Filter top signals
    
    Thresholds:
    - Volume spike: 3x+ historical average
    - Whale cluster: 3+ tracked whales
    - Momentum: 10%+ price change in 1h
    """
    
    def __init__(self, client: PolymarketDataClient):
        self.client = client
        # Cache: {condition_id: {"volume": float, "timestamp": datetime}}
        self._baseline_cache: dict[str, dict] = {}
        self._last_check: datetime = datetime.now()
    
    async def scan(
        self,
        lookback_hours: int = 2,
        min_volume_multiplier: float = 3.0,
        min_whale_count: int = 2,
    ) -> list[HotMarketSignal]:
        """Scan for hot markets with explosive activity.
        
        Args:
            lookback_hours: Recent activity window (default 2h)
            min_volume_multiplier: Min volume spike vs baseline (default 3x)
            min_whale_count: Min tracked whales required (default 2)
            
        Returns:
            List of HotMarketSignals, sorted by strength
        """
        try:
            cutoff = datetime.now() - timedelta(hours=lookback_hours)
            
            # Get tracked whale addresses
            with get_db() as db:
                whales = db.query(TrackedWallet).filter(
                    TrackedWallet.is_whale == True,
                    TrackedWallet.is_active == True,
                ).all()
                whale_addresses = {w.address.lower() for w in whales}
            
            if not whale_addresses:
                logger.debug("[HOT_MARKET] No tracked whales, skipping scan")
                return []
            
            # Fetch recent global activity
            # Strategy: Get activity from multiple whales to build market picture
            all_activity = []
            sample_whales = list(whale_addresses)[:10]  # Sample 10 whales
            
            tasks = [
                self.client.get_wallet_activity(wallet=whale, limit=100)
                for whale in sample_whales
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, Exception):
                    continue
                all_activity.extend(result)
            
            if not all_activity:
                logger.debug("[HOT_MARKET] No recent activity found")
                return []
            
            # Group activity by market
            markets: dict[str, dict] = defaultdict(lambda: {
                "trades": [],
                "whales": set(),
                "total_volume": 0.0,
                "title": "",
                "traders": set(),
            })
            
            for event in all_activity:
                event_type = event.get("type", "").upper()
                if event_type != "TRADE":
                    continue
                
                ts_raw = event.get("timestamp")
                if not ts_raw:
                    continue
                
                try:
                    if isinstance(ts_raw, (int, float)):
                        ts = datetime.fromtimestamp(ts_raw)
                    else:
                        ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                    
                    if ts < cutoff:
                        continue
                except Exception:
                    continue
                
                condition_id = event.get("conditionId", "")
                if not condition_id:
                    continue
                
                user = event.get("user", "").lower()
                side = event.get("side", "").upper()
                usdc_size = float(event.get("usdcSize", 0))
                
                if side != "BUY" or usdc_size == 0:
                    continue
                
                markets[condition_id]["trades"].append({
                    "timestamp": ts,
                    "user": user,
                    "usdc_size": usdc_size,
                    "price": float(event.get("price", 0)),
                })
                markets[condition_id]["total_volume"] += usdc_size
                markets[condition_id]["traders"].add(user)
                markets[condition_id]["title"] = event.get("title", "")[:100]
                
                if user in whale_addresses:
                    markets[condition_id]["whales"].add(user)
            
            # Analyze each market for hot signals
            signals: list[HotMarketSignal] = []
            
            for condition_id, data in markets.items():
                whale_count = len(data["whales"])
                if whale_count < min_whale_count:
                    continue
                
                recent_volume = data["total_volume"]
                if recent_volume < 1000:  # Skip low volume
                    continue
                
                # Get historical baseline
                baseline = await self._get_baseline_volume(
                    condition_id=condition_id,
                    recent_volume=recent_volume,
                )
                
                volume_multiplier = recent_volume / baseline if baseline > 0 else 10.0
                
                if volume_multiplier < min_volume_multiplier:
                    continue
                
                # Calculate metrics
                trades = data["trades"]
                whale_trades = [t for t in trades if t["user"] in whale_addresses]
                
                if not whale_trades:
                    continue
                
                avg_whale_amount = sum(t["usdc_size"] for t in whale_trades) / len(whale_trades)
                largest_trade = max((t["usdc_size"] for t in whale_trades), default=0)
                first_whale_entry = min((t["timestamp"] for t in whale_trades), default=datetime.now())
                
                # Price momentum (if we have enough data points)
                current_price = whale_trades[-1]["price"] if whale_trades else 0.5
                old_trades_1h = [t for t in trades if t["timestamp"] < (datetime.now() - timedelta(hours=1))]
                old_price = old_trades_1h[-1]["price"] if old_trades_1h else current_price
                price_change_1h = ((current_price - old_price) / old_price * 100) if old_price > 0 else 0
                
                # Determine signal type and strength
                signal_type = "WHALE_CLUSTER"
                strength = "MEDIUM"
                confidence = 0.60
                
                if whale_count >= 5:
                    strength = "EXTREME"
                    confidence = 0.90
                elif whale_count >= 3:
                    strength = "HIGH"
                    confidence = 0.75
                
                if volume_multiplier >= 10.0:
                    signal_type = "VOLUME_SPIKE"
                    strength = "EXTREME"
                    confidence = max(confidence, 0.85)
                elif volume_multiplier >= 5.0:
                    signal_type = "VOLUME_SPIKE"
                    confidence = max(confidence, 0.75)
                
                if abs(price_change_1h) >= 15.0:
                    signal_type = "MOMENTUM"
                    strength = "EXTREME"
                    confidence = max(confidence, 0.80)
                elif abs(price_change_1h) >= 10.0:
                    confidence = max(confidence, 0.70)
                
                signal = HotMarketSignal(
                    condition_id=condition_id,
                    title=data["title"],
                    signal_type=signal_type,
                    strength=strength,
                    confidence=confidence,
                    recent_volume_usdc=recent_volume,
                    historical_avg_volume=baseline,
                    volume_multiplier=volume_multiplier,
                    whale_count=whale_count,
                    total_traders=len(data["traders"]),
                    whale_addresses=list(data["whales"])[:5],
                    avg_whale_amount=avg_whale_amount,
                    largest_trade_usdc=largest_trade,
                    current_yes_price=current_price,
                    price_change_1h=price_change_1h,
                    first_whale_entry=first_whale_entry,
                    detection_timestamp=datetime.now(),
                )
                signals.append(signal)
            
            # Sort by confidence desc
            signals.sort(key=lambda s: s.confidence, reverse=True)
            
            self._last_check = datetime.now()
            
            if signals:
                logger.info(
                    f"[HOT_MARKET] Detected {len(signals)} hot markets | "
                    f"Top: {signals[0].title[:40]} ({signals[0].whale_count} whales, {signals[0].volume_multiplier:.1f}x vol)"
                )
            
            return signals
        
        except Exception as e:
            logger.warning(f"[HOT_MARKET] Scan failed: {e}")
            return []
    
    async def _get_baseline_volume(
        self,
        condition_id: str,
        recent_volume: float,
    ) -> float:
        """Get historical baseline volume for a market.
        
        Strategy:
        1. Check cache first
        2. If not in cache, use conservative baseline (recent_volume / 3)
        3. Update cache with recent volume for next scan
        
        This approach avoids expensive historical queries while still
        providing reasonable baseline estimates.
        """
        # Check cache
        if condition_id in self._baseline_cache:
            cached = self._baseline_cache[condition_id]
            # Cache valid for 24h
            if (datetime.now() - cached["timestamp"]).total_seconds() < 86400:
                return cached["volume"]
        
        # Conservative baseline: assume recent volume is 3x normal
        # This makes it harder to trigger false positives
        baseline = recent_volume / 3.0
        
        # Update cache for next scan
        self._baseline_cache[condition_id] = {
            "volume": recent_volume,  # Store actual volume observed
            "timestamp": datetime.now(),
        }
        
        # Limit cache size (keep last 100 markets)
        if len(self._baseline_cache) > 100:
            # Remove oldest entry
            oldest_key = min(
                self._baseline_cache.keys(),
                key=lambda k: self._baseline_cache[k]["timestamp"],
            )
            del self._baseline_cache[oldest_key]
        
        return baseline
    
    async def get_market_momentum(
        self,
        condition_id: str,
        hours: int = 6,
    ) -> Optional[dict]:
        """Get detailed momentum analysis for a specific market.
        
        Returns:
            Dict with volume_trend, price_trend, whale_activity
        """
        try:
            activity = await self.client.get_market_activity(
                condition_id=condition_id,
                limit=500,
            )
            
            if not activity:
                return None
            
            cutoff = datetime.now() - timedelta(hours=hours)
            
            # Get tracked whales
            with get_db() as db:
                whales = db.query(TrackedWallet).filter(
                    TrackedWallet.is_whale == True,
                    TrackedWallet.is_active == True,
                ).all()
                whale_addresses = {w.address.lower() for w in whales}
            
            # Analyze trades
            hourly_volume = defaultdict(float)
            hourly_whale_trades = defaultdict(int)
            prices = []
            
            for event in activity:
                event_type = event.get("type", "").upper()
                if event_type != "TRADE":
                    continue
                
                ts_raw = event.get("timestamp")
                if not ts_raw:
                    continue
                
                try:
                    if isinstance(ts_raw, (int, float)):
                        ts = datetime.fromtimestamp(ts_raw)
                    else:
                        ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                    
                    if ts < cutoff:
                        continue
                except Exception:
                    continue
                
                hour_key = ts.strftime("%Y-%m-%d %H:00")
                usdc_size = float(event.get("usdcSize", 0))
                price = float(event.get("price", 0))
                user = event.get("user", "").lower()
                
                hourly_volume[hour_key] += usdc_size
                
                if user in whale_addresses:
                    hourly_whale_trades[hour_key] += 1
                
                if price > 0:
                    prices.append({"timestamp": ts, "price": price})
            
            # Calculate trends
            volume_values = list(hourly_volume.values())
            volume_trend = "INCREASING" if len(volume_values) >= 2 and volume_values[-1] > volume_values[0] else "STABLE"
            
            price_trend = "STABLE"
            if len(prices) >= 2:
                first_price = prices[0]["price"]
                last_price = prices[-1]["price"]
                change_pct = ((last_price - first_price) / first_price * 100) if first_price > 0 else 0
                
                if change_pct > 5:
                    price_trend = "UP"
                elif change_pct < -5:
                    price_trend = "DOWN"
            
            whale_activity = "HIGH" if sum(hourly_whale_trades.values()) >= 10 else "NORMAL"
            
            return {
                "volume_trend": volume_trend,
                "price_trend": price_trend,
                "whale_activity": whale_activity,
                "total_volume": sum(volume_values),
                "whale_trades": sum(hourly_whale_trades.values()),
                "hourly_volume": dict(hourly_volume),
            }
        
        except Exception as e:
            logger.warning(f"[HOT_MARKET] Momentum analysis failed for {condition_id}: {e}")
            return None
