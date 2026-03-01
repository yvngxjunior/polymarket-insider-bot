"""Activity Analyzer - Advanced wallet analysis using complete /activity API.

PHASE 2: Leverages the complete /activity endpoint to:
1. Calculate entry timing scores (early entry = high score)
2. Accurate win rate calculation (includes REDEEM outcomes)
3. Pattern detection (SPLIT→SELL strategies)

This module provides scoring functions used by:
- WalletRefresher (during periodic refresh)
- WalletScanner (during initial wallet discovery)
- WhaleExitMonitor (for conviction scoring)
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from bot.config import get_settings
from bot.trading.polymarket import PolymarketDataClient
from bot.utils.logger import logger

settings = get_settings()


@dataclass
class EntryTimingResult:
    """Result of entry timing analysis."""
    wallet: str
    market_id: str
    entry_timestamp: datetime
    total_volume_before_entry: float  # USDC volume before wallet entered
    total_volume_after_entry: float   # USDC volume after wallet entered
    position_in_lifecycle: float      # 0.0 (first) to 1.0 (late)
    timing_score: float               # 0.0 (late) to 1.0 (early)
    

@dataclass
class WinRateResult:
    """Accurate win rate calculation result."""
    wallet: str
    total_markets: int
    winning_markets: int
    losing_markets: int
    ongoing_markets: int
    win_rate: float
    avg_hold_hours: float
    total_pnl_estimate: float  # Rough PnL estimate


@dataclass
class SplitSellPattern:
    """Detected SPLIT→SELL advanced strategy."""
    wallet: str
    market_id: str
    title: str
    split_timestamp: datetime
    sell_timestamp: datetime
    seconds_between: float
    sold_side: str  # "YES" or "NO"
    direction: str  # Implied bet direction
    confidence: float


class ActivityAnalyzer:
    """Advanced wallet analysis using complete /activity API.
    
    PHASE 2: Core analytics module for scoring wallets.
    """
    
    def __init__(self, client: PolymarketDataClient):
        self.client = client
    
    async def calculate_entry_timing_score(
        self,
        wallet: str,
        market_id: str,
        lookback_hours: int = 168,  # 7 days
    ) -> Optional[EntryTimingResult]:
        """Calculate entry timing score for a wallet on a specific market.
        
        Logic:
        1. Get all market activity
        2. Find when wallet first entered (BUY)
        3. Calculate total volume before vs after entry
        4. Score: early entry (< $5k volume before) = 0.9+
                  mid entry ($5k-$50k before) = 0.6-0.8
                  late entry (> $50k before) = 0.3-0.5
        
        Args:
            wallet: Wallet address to analyze
            market_id: Market condition_id
            lookback_hours: How far back to analyze (default 7 days)
            
        Returns:
            EntryTimingResult or None if wallet hasn't traded this market
        """
        try:
            # Get all market activity
            cutoff = datetime.now() - timedelta(hours=lookback_hours)
            
            market_activity = await self.client.get_market_activity(
                condition_id=market_id,
                limit=500,
            )
            
            if not market_activity:
                return None
            
            # Find wallet's first BUY on this market
            wallet_entry = None
            for event in reversed(market_activity):  # Chronological order
                ts_raw = event.get("timestamp")
                if not ts_raw:
                    continue
                
                try:
                    if isinstance(ts_raw, (int, float)):
                        ts = datetime.fromtimestamp(ts_raw)
                    else:
                        ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                except Exception:
                    continue
                
                if ts < cutoff:
                    continue
                
                event_user = event.get("user", "").lower()
                event_type = event.get("type", "").upper()
                event_side = event.get("side", "").upper()
                
                if (event_user == wallet.lower() and 
                    event_type == "TRADE" and 
                    event_side == "BUY"):
                    wallet_entry = {
                        "timestamp": ts,
                        "usdcSize": float(event.get("usdcSize", 0)),
                    }
                    break
            
            if not wallet_entry:
                return None
            
            entry_ts = wallet_entry["timestamp"]
            
            # Calculate volume before and after entry
            volume_before = 0.0
            volume_after = 0.0
            
            for event in market_activity:
                ts_raw = event.get("timestamp")
                if not ts_raw:
                    continue
                
                try:
                    if isinstance(ts_raw, (int, float)):
                        ts = datetime.fromtimestamp(ts_raw)
                    else:
                        ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                except Exception:
                    continue
                
                if ts < cutoff:
                    continue
                
                usdc_size = float(event.get("usdcSize", 0))
                
                if ts < entry_ts:
                    volume_before += usdc_size
                else:
                    volume_after += usdc_size
            
            # Calculate position in lifecycle
            total_volume = volume_before + volume_after
            if total_volume == 0:
                return None
            
            position = volume_before / total_volume
            
            # Calculate timing score
            if volume_before < 5000:
                timing_score = 0.95  # Extremely early
            elif volume_before < 10000:
                timing_score = 0.85
            elif volume_before < 25000:
                timing_score = 0.70
            elif volume_before < 50000:
                timing_score = 0.55
            else:
                timing_score = max(0.30, 1.0 - (position * 0.7))
            
            return EntryTimingResult(
                wallet=wallet,
                market_id=market_id,
                entry_timestamp=entry_ts,
                total_volume_before_entry=volume_before,
                total_volume_after_entry=volume_after,
                position_in_lifecycle=position,
                timing_score=timing_score,
            )
        
        except Exception as e:
            logger.warning(f"[ACTIVITY] Entry timing analysis failed for {wallet[:10]}: {e}")
            return None
    
    async def calculate_accurate_win_rate(
        self,
        wallet: str,
        lookback_days: int = 30,
    ) -> Optional[WinRateResult]:
        """Calculate accurate win rate using REDEEM events.
        
        PHASE 2: Proper win rate calculation.
        
        Logic:
        1. Get all wallet activity
        2. Group by market (BUY → EXIT pairs)
        3. For REDEEM exits: determine win/loss from outcome
        4. For SELL exits: estimate win/loss from price movement
        5. Calculate win rate
        
        Args:
            wallet: Wallet address
            lookback_days: Analysis period (default 30 days)
            
        Returns:
            WinRateResult with accurate statistics
        """
        try:
            activity = await self.client.get_wallet_activity(
                wallet=wallet,
                limit=500,
            )
            
            if not activity:
                return None
            
            cutoff = datetime.now() - timedelta(days=lookback_days)
            
            # Group by market
            markets: dict[str, dict] = {}
            
            for event in activity:
                ts_raw = event.get("timestamp")
                if not ts_raw:
                    continue
                
                try:
                    if isinstance(ts_raw, (int, float)):
                        ts = datetime.fromtimestamp(ts_raw)
                    else:
                        ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                except Exception:
                    continue
                
                if ts < cutoff:
                    continue
                
                market_id = event.get("conditionId", "")
                token_id = event.get("asset", "")
                if not market_id or not token_id:
                    continue
                
                key = f"{market_id}:{token_id}"
                
                if key not in markets:
                    markets[key] = {
                        "market_id": market_id,
                        "token_id": token_id,
                        "buys": [],
                        "exits": [],
                    }
                
                event_type = event.get("type", "").upper()
                event_side = event.get("side", "").upper()
                
                if event_type == "TRADE" and event_side == "BUY":
                    markets[key]["buys"].append({
                        "timestamp": ts,
                        "price": float(event.get("price", 0)),
                        "usdc_size": float(event.get("usdcSize", 0)),
                    })
                elif event_type == "TRADE" and event_side == "SELL":
                    markets[key]["exits"].append({
                        "timestamp": ts,
                        "type": "SELL",
                        "price": float(event.get("price", 0)),
                        "usdc_size": float(event.get("usdcSize", 0)),
                    })
                elif event_type == "REDEEM":
                    markets[key]["exits"].append({
                        "timestamp": ts,
                        "type": "REDEEM",
                        "price": 1.0,  # REDEEM means market resolved in your favor
                        "usdc_size": float(event.get("usdcSize", 0)),
                    })
            
            # Analyze each market
            winning = 0
            losing = 0
            ongoing = 0
            total_pnl = 0.0
            hold_times: list[float] = []
            
            for key, data in markets.items():
                if not data["buys"]:
                    continue
                
                if not data["exits"]:
                    ongoing += 1
                    continue
                
                # Use first buy and last exit
                entry = data["buys"][0]
                exit_event = data["exits"][-1]
                
                entry_price = entry["price"]
                exit_price = exit_event["price"]
                
                # Calculate PnL
                if exit_event["type"] == "REDEEM":
                    # REDEEM at price 1.0 means we won
                    pnl_pct = (1.0 - entry_price) / entry_price
                else:
                    # SELL
                    pnl_pct = (exit_price - entry_price) / entry_price if entry_price > 0 else 0
                
                if pnl_pct > 0:
                    winning += 1
                    total_pnl += entry["usdc_size"] * pnl_pct
                else:
                    losing += 1
                    total_pnl += entry["usdc_size"] * pnl_pct
                
                # Hold time
                hold_hours = (exit_event["timestamp"] - entry["timestamp"]).total_seconds() / 3600
                hold_times.append(hold_hours)
            
            total_closed = winning + losing
            if total_closed == 0:
                return None
            
            win_rate = winning / total_closed
            avg_hold = sum(hold_times) / len(hold_times) if hold_times else 0
            
            return WinRateResult(
                wallet=wallet,
                total_markets=total_closed + ongoing,
                winning_markets=winning,
                losing_markets=losing,
                ongoing_markets=ongoing,
                win_rate=win_rate,
                avg_hold_hours=avg_hold,
                total_pnl_estimate=total_pnl,
            )
        
        except Exception as e:
            logger.warning(f"[ACTIVITY] Win rate calculation failed for {wallet[:10]}: {e}")
            return None
    
    async def detect_split_sell_pattern(
        self,
        wallet: str,
        max_seconds_between: int = 300,  # 5 minutes
        lookback_days: int = 7,
    ) -> list[SplitSellPattern]:
        """Detect SPLIT→SELL advanced strategy patterns.
        
        PHASE 2: Advanced pattern detection.
        
        When a whale SPLITs (creates YES+NO from collateral) then immediately
        SELLs one side, it's a strong directional signal.
        
        Example:
        - SPLIT creates 1000 YES + 1000 NO
        - Immediately SELL 1000 YES
        - → Whale is betting on NO (keeping NO tokens)
        
        Args:
            wallet: Wallet address
            max_seconds_between: Max time between SPLIT and SELL (default 5 min)
            lookback_days: Analysis period
            
        Returns:
            List of detected patterns
        """
        try:
            activity = await self.client.get_wallet_activity(
                wallet=wallet,
                limit=200,
            )
            
            if not activity:
                return []
            
            cutoff = datetime.now() - timedelta(days=lookback_days)
            patterns: list[SplitSellPattern] = []
            
            # Sort by timestamp
            sorted_activity = sorted(
                activity,
                key=lambda x: x.get("timestamp", 0),
            )
            
            for i, event in enumerate(sorted_activity):
                event_type = event.get("type", "").upper()
                if event_type != "SPLIT":
                    continue
                
                ts_raw = event.get("timestamp")
                if not ts_raw:
                    continue
                
                try:
                    if isinstance(ts_raw, (int, float)):
                        split_ts = datetime.fromtimestamp(ts_raw)
                    else:
                        split_ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                except Exception:
                    continue
                
                if split_ts < cutoff:
                    continue
                
                split_market = event.get("conditionId", "")
                if not split_market:
                    continue
                
                # Look for immediate SELL on same market
                for j in range(i + 1, min(i + 5, len(sorted_activity))):
                    next_event = sorted_activity[j]
                    
                    next_type = next_event.get("type", "").upper()
                    next_side = next_event.get("side", "").upper()
                    
                    if next_type != "TRADE" or next_side != "SELL":
                        continue
                    
                    next_market = next_event.get("conditionId", "")
                    if next_market != split_market:
                        continue
                    
                    ts_raw = next_event.get("timestamp")
                    if not ts_raw:
                        continue
                    
                    try:
                        if isinstance(ts_raw, (int, float)):
                            sell_ts = datetime.fromtimestamp(ts_raw)
                        else:
                            sell_ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                    except Exception:
                        continue
                    
                    seconds_diff = (sell_ts - split_ts).total_seconds()
                    if seconds_diff > max_seconds_between:
                        break
                    
                    # Pattern detected!
                    sold_token = next_event.get("asset", "")
                    sold_side = "YES" if "YES" in sold_token.upper() else "NO"
                    direction = "NO" if sold_side == "YES" else "YES"
                    
                    # Confidence based on time gap (faster = higher confidence)
                    confidence = max(0.70, 0.95 - (seconds_diff / max_seconds_between) * 0.25)
                    
                    pattern = SplitSellPattern(
                        wallet=wallet,
                        market_id=split_market,
                        title=event.get("title", "")[:60],
                        split_timestamp=split_ts,
                        sell_timestamp=sell_ts,
                        seconds_between=seconds_diff,
                        sold_side=sold_side,
                        direction=direction,
                        confidence=confidence,
                    )
                    patterns.append(pattern)
                    break
            
            return patterns
        
        except Exception as e:
            logger.warning(f"[ACTIVITY] SPLIT-SELL detection failed for {wallet[:10]}: {e}")
            return []
