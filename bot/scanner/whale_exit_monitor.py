"""Whale Exit Monitor - Tracks REDEEM/SELL events from tracked whales.

This module monitors when whales exit positions (REDEEM after resolution,
or SELL before resolution) to provide early warning signals.

Two modes:
1. Passive: Analyze exit patterns for scoring
2. Active: Alert when whale exits a market we're holding

PHASE 1: Now uses complete /activity API to capture:
- SELL (early exit before resolution)
- REDEEM (claim winnings after market resolves)
- SPLIT/MERGE (advanced strategies)

Docs:
- /activity REDEEM schema: https://docs.polymarket.com/developers/misc-endpoints/data-api-activity
- Exit strategies: https://news.stand.trade/p/redeeming-vs-splitting-vs-merging
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from bot.config import get_settings
from bot.database import get_db, TrackedWallet, CopiedTrade, TradeStatus
from bot.trading.polymarket import PolymarketDataClient
from bot.utils.logger import logger

settings = get_settings()


@dataclass
class WhaleExitEvent:
    """Represents a whale exit (REDEEM or SELL)."""
    wallet: str
    condition_id: str
    token_id: str
    exit_type: str  # "REDEEM" or "SELL"
    price: float
    amount_usdc: float
    timestamp: datetime
    title: str
    matches_our_position: bool = False
    trade_id: Optional[int] = None  # CopiedTrade.id if matches


@dataclass
class WhaleExitStats:
    """Exit behavior statistics for a whale wallet."""
    wallet: str
    total_exits: int
    redeem_count: int  # Hold to resolution
    sell_count: int  # Early exit
    avg_hold_hours: float
    early_exit_rate: float  # % of positions sold early
    conviction_score: float  # 0-1, higher = stronger conviction


class WhaleExitMonitor:
    """Monitors whale exit events (REDEEM/SELL) for signals.
    
    PHASE 1: Enhanced with complete /activity API support.
    Now properly captures REDEEM events (not just SELL).
    
    Features:
    - Track REDEEM (held to resolution) vs SELL (early exit)
    - Calculate hold time and conviction metrics
    - Alert when whale exits a market we're holding
    - Optional auto-exit on whale SELL signal
    """

    def __init__(self, client: PolymarketDataClient):
        self.client = client
        # Cache: {wallet: {condition_id: last_check_timestamp}}
        self._last_check: dict[str, dict[str, datetime]] = {}

    async def check_whale_exits(
        self,
        whale_addresses: list[str],
        since_hours: int = 6
    ) -> list[WhaleExitEvent]:
        """Check for recent exits from tracked whales.
        
        PHASE 1: Now uses get_wallet_activity() instead of get_wallet_trades()
        to capture REDEEM events properly.
        
        Args:
            whale_addresses: List of whale wallet addresses to monitor
            since_hours: Look back window in hours
            
        Returns:
            List of WhaleExitEvents found
        """
        if not settings.whale_exit_tracking:
            return []

        cutoff = datetime.now() - timedelta(hours=since_hours)
        exit_events: list[WhaleExitEvent] = []

        # Check exits for each whale
        tasks = [
            self._check_wallet_exits(wallet, cutoff)
            for wallet in whale_addresses
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"[WHALE_EXIT] Check failed: {result}")
                continue
            exit_events.extend(result)

        # Match against our open positions
        if exit_events:
            exit_events = await self._match_to_positions(exit_events)

        return exit_events

    async def _check_wallet_exits(
        self,
        wallet: str,
        cutoff: datetime
    ) -> list[WhaleExitEvent]:
        """Check single wallet for recent exits.
        
        PHASE 1: Uses get_wallet_activity() to capture ALL activity types.
        Filters for SELL (type=TRADE + side=SELL) and REDEEM (type=REDEEM).
        """
        try:
            # PHASE 1: Use complete /activity API (no type filter)
            activity = await self.client.get_wallet_activity(
                wallet=wallet,
                limit=100,
                event_type=None,  # Get all types
            )
            
            exits: list[WhaleExitEvent] = []
            for event in activity:
                event_type = event.get("type", "").upper()
                
                # PHASE 1: Capture both SELL (from TRADE events) and REDEEM
                is_sell = (event_type == "TRADE" and event.get("side", "").upper() == "SELL")
                is_redeem = (event_type == "REDEEM")
                
                if not (is_sell or is_redeem):
                    continue

                # Parse timestamp
                ts_raw = event.get("timestamp")
                if not ts_raw:
                    continue
                    
                try:
                    # Handle both ISO string and unix timestamp
                    if isinstance(ts_raw, (int, float)):
                        ts = datetime.fromtimestamp(ts_raw)
                    else:
                        ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                    
                    if ts < cutoff:
                        continue
                except Exception as e:
                    logger.debug(f"[WHALE_EXIT] Timestamp parse error: {e}")
                    continue

                # Check if we already processed this exit
                condition_id = event.get("conditionId", "")
                if not condition_id:
                    continue
                    
                wallet_cache = self._last_check.get(wallet, {})
                last_check = wallet_cache.get(condition_id)
                if last_check and ts <= last_check:
                    continue

                # Build exit event
                size = float(event.get("size", 0))
                price = float(event.get("price", 0))
                usdc_size = float(event.get("usdcSize", 0))
                
                # Estimate USDC amount
                if usdc_size == 0 and size > 0:
                    # For REDEEM, price is 1.0 or 0.0 depending on outcome
                    if is_redeem:
                        # Assume winning outcome for estimation
                        usdc_size = size  # 1 token = 1 USDC on winning side
                    elif price > 0:
                        usdc_size = size * price

                exit_event = WhaleExitEvent(
                    wallet=wallet,
                    condition_id=condition_id,
                    token_id=event.get("asset", ""),
                    exit_type="REDEEM" if is_redeem else "SELL",
                    price=price if not is_redeem else (1.0 if size > 0 else 0.0),
                    amount_usdc=usdc_size,
                    timestamp=ts,
                    title=event.get("title", "")[:60],
                )
                exits.append(exit_event)

                # Update cache
                if wallet not in self._last_check:
                    self._last_check[wallet] = {}
                self._last_check[wallet][condition_id] = ts

            return exits

        except Exception as e:
            logger.warning(f"[WHALE_EXIT] Failed to check {wallet[:10]}: {e}")
            return []

    async def _match_to_positions(
        self,
        exit_events: list[WhaleExitEvent]
    ) -> list[WhaleExitEvent]:
        """Match exit events to our open positions (CopiedTrade with status=EXECUTED)."""
        try:
            with get_db() as db:
                # Get open positions (executed trades without PnL)
                open_trades = db.query(CopiedTrade).filter(
                    CopiedTrade.status == TradeStatus.EXECUTED,
                    CopiedTrade.pnl_usdc.is_(None),  # Not closed yet
                ).all()

                for event in exit_events:
                    for trade in open_trades:
                        # Match by market_id (condition_id) and token_id
                        if (event.condition_id == trade.market_id
                            and event.token_id == trade.token_id):
                            event.matches_our_position = True
                            event.trade_id = trade.id
                            break

        except Exception as e:
            logger.warning(f"[WHALE_EXIT] Position matching failed: {e}")

        return exit_events

    async def analyze_exit_patterns(
        self,
        wallet: str,
        lookback_days: int = 30
    ) -> Optional[WhaleExitStats]:
        """Analyze exit behavior for a wallet.
        
        PHASE 1: Now properly distinguishes REDEEM from SELL.
        
        Calculates:
        - Redeem rate (held to resolution)
        - Sell rate (early exit before resolution)
        - Average hold time
        - Conviction score (higher = better)
        """
        try:
            # PHASE 1: Get complete activity (all types)
            activity = await self.client.get_wallet_activity(
                wallet=wallet,
                limit=300,
            )
            
            cutoff = datetime.now() - timedelta(days=lookback_days)
            
            buys = []
            exits = []
            
            for event in activity:
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

                event_type = event.get("type", "").upper()
                
                if event_type == "TRADE" and event.get("side", "").upper() == "BUY":
                    buys.append({
                        "condition_id": event.get("conditionId", ""),
                        "token_id": event.get("asset", ""),
                        "timestamp": ts,
                    })
                elif event_type == "TRADE" and event.get("side", "").upper() == "SELL":
                    exits.append({
                        "condition_id": event.get("conditionId", ""),
                        "token_id": event.get("asset", ""),
                        "timestamp": ts,
                        "type": "SELL",
                    })
                elif event_type == "REDEEM":
                    exits.append({
                        "condition_id": event.get("conditionId", ""),
                        "token_id": event.get("asset", ""),
                        "timestamp": ts,
                        "type": "REDEEM",
                    })

            if not exits:
                return None

            # Match BUY → EXIT pairs
            hold_times: list[float] = []
            redeem_count = 0
            sell_count = 0

            for exit in exits:
                # Find matching BUY
                for buy in buys:
                    if (buy["condition_id"] == exit["condition_id"]
                        and buy["token_id"] == exit["token_id"]
                        and buy["timestamp"] < exit["timestamp"]):
                        
                        hold_hours = (exit["timestamp"] - buy["timestamp"]).total_seconds() / 3600
                        hold_times.append(hold_hours)
                        
                        if exit["type"] == "REDEEM":
                            redeem_count += 1
                        else:
                            sell_count += 1
                        
                        break

            total_exits = redeem_count + sell_count
            if total_exits == 0:
                return None

            avg_hold_hours = sum(hold_times) / len(hold_times) if hold_times else 0
            early_exit_rate = sell_count / total_exits
            
            # Conviction score: high redeem rate + long hold = high conviction
            redeem_rate = redeem_count / total_exits
            hold_score = min(1.0, avg_hold_hours / 48.0)  # 48h = max score
            conviction_score = (redeem_rate * 0.7) + (hold_score * 0.3)

            return WhaleExitStats(
                wallet=wallet,
                total_exits=total_exits,
                redeem_count=redeem_count,
                sell_count=sell_count,
                avg_hold_hours=avg_hold_hours,
                early_exit_rate=early_exit_rate,
                conviction_score=conviction_score,
            )

        except Exception as e:
            logger.warning(f"[WHALE_EXIT] Pattern analysis failed for {wallet[:10]}: {e}")
            return None

    async def enrich_whale_scores(self) -> dict[str, float]:
        """Update whale scores based on exit behavior.
        
        Returns:
            Dict mapping wallet address to conviction_score adjustment
        """
        adjustments: dict[str, float] = {}

        try:
            with get_db() as db:
                whales = db.query(TrackedWallet).filter(
                    TrackedWallet.is_whale == True,
                    TrackedWallet.is_active == True,
                ).all()

                for whale in whales:
                    stats = await self.analyze_exit_patterns(whale.address)
                    if stats:
                        # Adjust score: high conviction = boost, low = penalty
                        if stats.conviction_score > 0.75:
                            adjustments[whale.address] = +0.05
                        elif stats.conviction_score < 0.40:
                            adjustments[whale.address] = -0.10
                        
                        logger.info(
                            f"[WHALE_EXIT] {whale.address[:10]}... | "
                            f"Conviction: {stats.conviction_score:.2f} | "
                            f"Redeem: {stats.redeem_count}/{stats.total_exits} ({stats.redeem_count/stats.total_exits:.0%}) | "
                            f"Sell: {stats.sell_count}/{stats.total_exits} ({stats.early_exit_rate:.0%}) | "
                            f"Hold: {stats.avg_hold_hours:.1f}h"
                        )

        except Exception as e:
            logger.warning(f"[WHALE_EXIT] Score enrichment failed: {e}")

        return adjustments
