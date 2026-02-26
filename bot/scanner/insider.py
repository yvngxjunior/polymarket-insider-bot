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
    """
    FIX INSIDER-1: conversion float robuste.
    Evite float(None) -> TypeError quand l'API retourne null
    sur les champs usdcSize / tradeSize.
    """
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class InsiderScanner:
    """
    Detecte les wallets a haut win-rate (insiders potentiels).
    Win rate pondere par recence, series de pertes, score de timing.

    FIX #7        -- consecutive_losses : remis a 0 des qu'un trade gagnant est detecte.
    FIX INSIDER-1 -- _safe_float() evite TypeError sur usdcSize/tradeSize null.
    FIX INSIDER-2 -- _known_trades n'indexe plus les id vides ('').
    FIX INSIDER-3 -- refresh_tracked_wallets() limite la concurrence (Semaphore 20).
    FIX BUG-2     -- Add debug logs + case-insensitive type check for BUY.
    """

    def __init__(self, client: PolymarketDataClient):
        self.client = client
        self._known_trades: dict[str, set[str]] = {}

    async def analyze_wallet(self, wallet_address: str) -> WalletAnalysis:
        trades = await self.client.get_wallet_trades(wallet_address, limit=300)
        if not trades:
            return self._empty_analysis(wallet_address, "No trade history")

        resolved = [t for t in trades if t.get("type") in ("REDEEM", "SELL")]
        total = len(resolved)

        if total < settings.min_trades_count:
            return self._empty_analysis(
                wallet_address,
                f"Not enough trades ({total} < {settings.min_trades_count})"
            )

        # FIX INSIDER-1: _safe_float() a la place de float(..., 0)
        # -> robuste si l'API retourne null sur usdcSize ou tradeSize
        profitable_trades = [
            t for t in resolved
            if _safe_float(t.get("usdcSize")) > _safe_float(t.get("tradeSize"))
        ]
        win_rate = len(profitable_trades) / total

        weighted_wins = sum(
            _decay_weight(t.get("timestamp"))
            for t in resolved
            if _safe_float(t.get("usdcSize")) > _safe_float(t.get("tradeSize"))
        )
        total_weight = sum(_decay_weight(t.get("timestamp")) for t in resolved)
        win_rate_weighted = weighted_wins / total_weight if total_weight > 0 else 0

        # FIX #7 -- calcul strict : on parcourt les trades recents dans l'ordre
        # et on s'arrete des le premier trade gagnant.
        recent = sorted(resolved, key=lambda t: t.get("timestamp", ""), reverse=True)[:10]
        consecutive_losses = 0
        for t in recent:
            is_loss = _safe_float(t.get("usdcSize")) <= _safe_float(t.get("tradeSize"))
            if is_loss:
                consecutive_losses += 1
            else:
                break

        profits = [
            _safe_float(t.get("usdcSize")) - _safe_float(t.get("tradeSize"))
            for t in resolved
        ]
        total_profit = sum(profits)
        avg_profit   = total_profit / total if total > 0 else 0

        entry_prices = [
            _safe_float(t.get("price"), 0.5)
            for t in profitable_trades
            if _safe_float(t.get("price")) > 0
        ]
        if entry_prices:
            avg_entry          = sum(entry_prices) / len(entry_prices)
            entry_timing_score = max(0.0, min(1.0, 1 - (avg_entry / 0.6)))
        else:
            entry_timing_score = 0.5

        score = score_wallet(win_rate_weighted, total, total_profit)
        label = get_score_label(score)

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
        # FIX INSIDER-2: filtre les id vides pour eviter de marquer
        # tous les futurs trades sans id comme 'deja connus'
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
        """
        FIX BUG-2: Debug logs + case-insensitive type check.
        Returns only NEW BUY trades from wallet_address.
        """
        trades = await self.client.get_wallet_trades(wallet_address, limit=20)
        known  = self._known_trades.get(wallet_address, set())
        new_trades = []
        
        for trade in trades:
            trade_id = trade.get("id", "")
            trade_type = (trade.get("type") or "").upper()  # Case-insensitive
            
            # FIX BUG-2: Log pour debug
            if trade_id and trade_id not in known:
                logger.debug(
                    f"[SCAN] {wallet_address[:10]} new trade detected: "
                    f"type={trade_type} id={trade_id[:12]}... "
                    f"amount=${_safe_float(trade.get('usdcSize')):.2f}"
                )
            
            if trade_id and trade_id not in known:
                if trade_type == "BUY":  # Case-insensitive check
                    new_trades.append(trade)
                    logger.info(
                        f"[NEW TRADE] {wallet_address[:10]}... BUY "
                        f"${_safe_float(trade.get('usdcSize')):.2f} "
                        f"@ {_safe_float(trade.get('price')):.3f} "
                        f"on {trade.get('asset', '?')[:16]}..."
                    )
                known.add(trade_id)
        
        self._known_trades[wallet_address] = known
        return new_trades

    async def refresh_tracked_wallets(self) -> list[WalletAnalysis]:
        logger.info("Starting full wallet refresh...")
        top_traders = await self.client.get_top_traders(limit=300)

        # FIX INSIDER-3: Semaphore pour limiter la concurrence
        # L'ancienne version lancait jusqu'a 300 requetes HTTP simultanees
        # -> risque de rate-limit ou ban temporaire de l'API Polymarket.
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
                        # FIX #7 -- persiste le consecutive_losses meme en cas de desactivation
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

                wallet.win_rate            = analysis.win_rate_weighted
                wallet.total_trades        = analysis.total_trades
                wallet.total_profit_usd    = analysis.total_profit_usd
                wallet.score               = analysis.score
                wallet.is_active           = True
                wallet.consecutive_losses  = analysis.consecutive_losses
                wallet.entry_timing_score  = analysis.entry_timing_score
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
