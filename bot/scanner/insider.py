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


class InsiderScanner:
    """
    Détecte les wallets à haut win-rate (insiders potentiels).
    Win rate pondéré par récence, séries de pertes, score de timing.
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

        profitable_trades = [
            t for t in resolved
            if float(t.get("usdcSize", 0)) > float(t.get("tradeSize", 0))
        ]
        win_rate = len(profitable_trades) / total

        weighted_wins = sum(
            _decay_weight(t.get("timestamp"))
            for t in resolved
            if float(t.get("usdcSize", 0)) > float(t.get("tradeSize", 0))
        )
        total_weight = sum(_decay_weight(t.get("timestamp")) for t in resolved)
        win_rate_weighted = weighted_wins / total_weight if total_weight > 0 else 0

        recent = sorted(resolved, key=lambda t: t.get("timestamp", ""), reverse=True)[:10]
        consecutive_losses = 0
        for t in recent:
            if float(t.get("usdcSize", 0)) <= float(t.get("tradeSize", 0)):
                consecutive_losses += 1
            else:
                break

        profits = [
            float(t.get("usdcSize", 0)) - float(t.get("tradeSize", 0))
            for t in resolved
        ]
        total_profit = sum(profits)
        avg_profit = total_profit / total if total > 0 else 0

        entry_prices = [
            float(t.get("price", 0.5))
            for t in profitable_trades
            if float(t.get("price", 0)) > 0
        ]
        if entry_prices:
            avg_entry = sum(entry_prices) / len(entry_prices)
            entry_timing_score = max(0, 1 - (avg_entry / 0.6))
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
        self._known_trades[wallet_address] = {t.get("id", "") for t in trades}

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
        trades = await self.client.get_wallet_trades(wallet_address, limit=20)
        known = self._known_trades.get(wallet_address, set())
        new_trades = []
        for trade in trades:
            trade_id = trade.get("id", "")
            if trade_id and trade_id not in known:
                # FIX: filtre les trades de type BUY uniquement — on ne doit pas copier
                # des SELL/REDEEM de l'insider (ce sont des sorties de position, pas des
                # nouvelles entrées). L'ancienne version retournait tous les types.
                if trade.get("type", "").upper() == "BUY":
                    new_trades.append(trade)
                known.add(trade_id)
        self._known_trades[wallet_address] = known
        return new_trades

    async def refresh_tracked_wallets(self) -> list[WalletAnalysis]:
        logger.info("Starting full wallet refresh...")
        top_traders = await self.client.get_top_traders(limit=300)
        tasks = [
            self.analyze_wallet(trader.get("proxyWalletAddress", ""))
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
                        logger.warning(f"⚠️ Wallet {analysis.address[:8]}... DEACTIVATED")
                    continue

                wallet = db.get(TrackedWallet, analysis.address)
                if wallet is None:
                    wallet = TrackedWallet(address=analysis.address)
                    db.add(wallet)
                    logger.info(
                        f"✨ New insider: {analysis.address[:8]}... {analysis.score_label} "
                        f"| WR: {analysis.win_rate_weighted:.0%}"
                    )

                wallet.win_rate = analysis.win_rate_weighted
                wallet.total_trades = analysis.total_trades
                wallet.total_profit_usd = analysis.total_profit_usd
                wallet.score = analysis.score
                wallet.is_active = True
                # FIX: persiste les champs maintenant déclarés dans le modèle
                wallet.consecutive_losses = analysis.consecutive_losses
                wallet.entry_timing_score = analysis.entry_timing_score
                results.append(analysis)

        logger.info(f"Refresh done. {len(results)} qualified wallets.")
        return results

    def _empty_analysis(self, address: str, reason: str) -> WalletAnalysis:
        return WalletAnalysis(
            address=address, win_rate=0, win_rate_weighted=0, total_trades=0,
            total_profit_usd=0, avg_profit_per_trade=0, score=0,
            score_label="🔴 D (Weak)", is_qualified=False,
            consecutive_losses=0, entry_timing_score=0,
            disqualify_reason=reason
        )
