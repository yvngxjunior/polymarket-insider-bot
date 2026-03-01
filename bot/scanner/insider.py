import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from bot.config import get_settings
from bot.database import get_db, TrackedWallet
from bot.trading.polymarket import PolymarketDataClient
from bot.utils.helpers import score_wallet, get_score_label
from bot.utils.logger import logger

settings = get_settings()

DECAY_HALF_LIFE_DAYS = 30

# FIX INSIDER-3: limite la concurrence lors du refresh pour eviter
# le rate-limit API (300 requetes simultanees -> ban temporaire)
_REFRESH_SEMAPHORE_SIZE = 20


@dataclass
class WalletAnalysis:
    address: str
    win_rate: float
    win_rate_weighted: float
    total_trades: int
    total_profit_usd: float
    avg_profit_per_trade: float
    score: float
    score_label: str
    is_qualified: bool
    consecutive_losses: int
    entry_timing_score: float
    latest_trade: Optional[dict] = None
    disqualify_reason: str = ""


def _decay_weight(trade_timestamp: Optional[str]) -> float:
    if not trade_timestamp:
        return 0.5
    try:
        ts = datetime.fromisoformat(trade_timestamp.replace("Z", "+00:00"))
        age_days = (datetime.now().astimezone() - ts).days
        return 0.5 ** (age_days / DECAY_HALF_LIFE_DAYS)
    except Exception:
        return 0.5


def _safe_float(value, default: float = 0.0) -> float:
    """Robust float conversion for Polymarket API numeric fields.
    
    Official docs specify numeric fields like `size`, `usdcSize`, and `price`
    as numbers, but older payloads or edge-cases can contain null/strings.
    This helper prevents TypeError/ValueError in those cases.
    """
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class InsiderScanner:
    """Detects high win-rate wallets (potential insiders) on Polymarket.
    
    Win rate calculated using proper /activity schema:
    - Entry cost (BUY): size * price
    - Exit value (REDEEM/SELL): usdcSize
    - Profit: usdcSize - (size * price)
    
    Official docs:
    - /activity schema: https://docs.polymarket.com/developers/misc-endpoints/data-api-activity
    - Fields: type, size (tokens), usdcSize (USDC.e), price (0-1), asset, side
    
    FIXES:
    - FIX #7        -- consecutive_losses reset on first win
    - FIX INSIDER-1 -- _safe_float() prevents TypeError on null fields
    - FIX INSIDER-2 -- _known_trades filters empty IDs
    - FIX INSIDER-3 -- Semaphore(20) prevents API rate-limit
    - FIX INSIDER-4 -- Correct PnL: removed non-existent 'tradeSize' field,
                       now uses size*price (entry cost) vs usdcSize (exit value)
    """

    def __init__(self, client: PolymarketDataClient):
        self.client = client
        self._known_trades: dict[str, set[str]] = {}

    async def analyze_wallet(self, wallet_address: str) -> WalletAnalysis:
        """Analyze wallet performance using official /activity endpoint schema.
        
        PnL calculation aligned with Polymarket Data-API:
        1. Filter resolved trades (type=REDEEM or SELL)
        2. Calculate entry cost: size * price (shares bought * entry price)
        3. Calculate exit value: usdcSize (USDC received on exit)
        4. Profit: exit_value - entry_cost
        
        This matches community best practices for insider tracking.
        """
        trades = await self.client.get_wallet_trades(wallet_address, limit=300)
        if not trades:
            return self._empty_analysis(wallet_address, "No trade history")

        # Filter resolved positions (closed trades)
        resolved = [t for t in trades if t.get("type") in ("REDEEM", "SELL")]
        total = len(resolved)

        if total < settings.min_trades_count:
            return self._empty_analysis(
                wallet_address,
                f"Not enough trades ({total} < {settings.min_trades_count})"
            )

        # FIX INSIDER-4: Correct PnL calculation using official schema
        # Entry cost = size * price (tokens bought × entry price)
        # Exit value = usdcSize (USDC.e received on close)
        # Profitable = exit > entry
        profitable_trades = []
        for t in resolved:
            size = _safe_float(t.get("size"))
            price = _safe_float(t.get("price"))
            usdc_size = _safe_float(t.get("usdcSize"))
            
            # Entry cost in USDC
            entry_cost = size * price
            
            # Profitable if exit value > entry cost
            if usdc_size > entry_cost:
                profitable_trades.append(t)
        
        win_rate = len(profitable_trades) / total if total > 0 else 0

        # Weighted win rate (decay by recency)
        weighted_wins = 0.0
        total_weight = 0.0
        for t in resolved:
            weight = _decay_weight(t.get("timestamp"))
            total_weight += weight
            
            size = _safe_float(t.get("size"))
            price = _safe_float(t.get("price"))
            usdc_size = _safe_float(t.get("usdcSize"))
            entry_cost = size * price
            
            if usdc_size > entry_cost:
                weighted_wins += weight
        
        win_rate_weighted = weighted_wins / total_weight if total_weight > 0 else 0

        # FIX #7 -- Consecutive losses: stop at first win
        recent = sorted(resolved, key=lambda t: t.get("timestamp", ""), reverse=True)[:10]
        consecutive_losses = 0
        for t in recent:
            size = _safe_float(t.get("size"))
            price = _safe_float(t.get("price"))
            usdc_size = _safe_float(t.get("usdcSize"))
            entry_cost = size * price
            
            is_loss = usdc_size <= entry_cost
            if is_loss:
                consecutive_losses += 1
            else:
                break

        # Total profit calculation
        profits = []
        for t in resolved:
            size = _safe_float(t.get("size"))
            price = _safe_float(t.get("price"))
            usdc_size = _safe_float(t.get("usdcSize"))
            entry_cost = size * price
            profit = usdc_size - entry_cost
            profits.append(profit)
        
        total_profit = sum(profits)
        avg_profit = total_profit / total if total > 0 else 0

        # Entry timing score (lower entry price = better timing)
        entry_prices = [
            _safe_float(t.get("price"), 0.5)
            for t in profitable_trades
            if _safe_float(t.get("price")) > 0
        ]
        if entry_prices:
            avg_entry = sum(entry_prices) / len(entry_prices)
            # Lower average entry price = higher timing score
            entry_timing_score = max(0.0, min(1.0, 1 - (avg_entry / 0.6)))
        else:
            entry_timing_score = 0.5

        score = score_wallet(win_rate_weighted, total, total_profit)
        label = get_score_label(score)

        # Disqualify on losing streak
        if consecutive_losses >= 5:
            return WalletAnalysis(
                address=wallet_address, win_rate=win_rate,
                win_rate_weighted=win_rate_weighted, total_trades=total,
                total_profit_usd=total_profit, avg_profit_per_trade=avg_profit,
                score=score, score_label=label, is_qualified=False,
                consecutive_losses=consecutive_losses,
                entry_timing_score=entry_timing_score,
                latest_trade=trades[0] if trades else None,
                disqualify_reason=f"Losing streak: {consecutive_losses} consecutive losses"
            )

        qualified = (
            win_rate_weighted >= settings.min_win_rate
            and avg_profit >= 1.0
        )
        
        # FIX INSIDER-2: Filter empty IDs to prevent false positives
        self._known_trades[wallet_address] = {
            t.get("id") for t in trades if t.get("id")
        }

        return WalletAnalysis(
            address=wallet_address, win_rate=win_rate,
            win_rate_weighted=win_rate_weighted, total_trades=total,
            total_profit_usd=total_profit, avg_profit_per_trade=avg_profit,
            score=score, score_label=label, is_qualified=qualified,
            consecutive_losses=consecutive_losses,
            entry_timing_score=entry_timing_score,
            latest_trade=trades[0] if trades else None,
            disqualify_reason="" if qualified else
                f"WR weighted: {win_rate_weighted:.0%} or avg profit too low (${avg_profit:.2f})"
        )

    async def get_new_trades(self, wallet_address: str) -> list[dict]:
        """Fetch new BUY trades for copy-trading.
        
        Only tracks type=BUY from /activity endpoint for real-time signal.
        """
        trades = await self.client.get_wallet_trades(wallet_address, limit=20)
        known = self._known_trades.get(wallet_address, set())
        new_trades = []
        for trade in trades:
            trade_id = trade.get("id", "")
            if trade_id and trade_id not in known:
                if trade.get("type", "").upper() == "BUY":
                    new_trades.append(trade)
                known.add(trade_id)
        self._known_trades[wallet_address] = known
        return new_trades

    async def refresh_tracked_wallets(self) -> list[WalletAnalysis]:
        """Refresh all tracked wallets from leaderboard.
        
        FIX INSIDER-3: Uses Semaphore(20) to prevent API rate-limit.
        """
        logger.info("Starting full wallet refresh...")
        top_traders = await self.client.get_top_traders(limit=300)

        # FIX INSIDER-3: Rate-limit protection
        sem = asyncio.Semaphore(_REFRESH_SEMAPHORE_SIZE)

        async def _analyze_with_sem(address: str) -> WalletAnalysis:
            async with sem:
                return await self.analyze_wallet(address)

        tasks = [
            _analyze_with_sem(trader.get("proxyWalletAddress", ""))
            for trader in top_traders
            if trader.get("proxyWalletAddress")
        ]
        analyses = await asyncio.gather(*tasks, return_exceptions=True)

        results = []
        with get_db() as db:
            for analysis in analyses:
                if isinstance(analysis, Exception):
                    logger.warning(f"Wallet analysis failed: {analysis}")
                    continue
                if not analysis.is_qualified:
                    existing = db.get(TrackedWallet, analysis.address)
                    if existing and existing.is_active and analysis.consecutive_losses >= 5:
                        existing.is_active = False
                        # FIX #7 -- Persist consecutive_losses on deactivation
                        existing.consecutive_losses = analysis.consecutive_losses
                        logger.warning(f"Wallet {analysis.address[:8]}... DEACTIVATED")
                    continue

                wallet = db.get(TrackedWallet, analysis.address)
                if wallet is None:
                    wallet = TrackedWallet(address=analysis.address)
                    db.add(wallet)
                    logger.info(
                        f"New insider: {analysis.address[:8]}... {analysis.score_label} "
                        f"| WR: {analysis.win_rate_weighted:.0%}"
                    )

                wallet.win_rate = analysis.win_rate_weighted
                wallet.total_trades = analysis.total_trades
                wallet.total_profit_usd = analysis.total_profit_usd
                wallet.score = analysis.score
                wallet.is_active = True
                wallet.consecutive_losses = analysis.consecutive_losses
                wallet.entry_timing_score = analysis.entry_timing_score
                results.append(analysis)

        logger.info(f"Refresh done. {len(results)} qualified wallets.")
        return results

    def _empty_analysis(self, address: str, reason: str) -> WalletAnalysis:
        return WalletAnalysis(
            address=address, win_rate=0, win_rate_weighted=0, total_trades=0,
            total_profit_usd=0, avg_profit_per_trade=0, score=0,
            score_label="D (Weak)", is_qualified=False,
            consecutive_losses=0, entry_timing_score=0,
            disqualify_reason=reason
        )
