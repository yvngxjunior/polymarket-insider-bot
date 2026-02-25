import asyncio
from dataclasses import dataclass, field
from typing import Optional

from bot.config import get_settings
from bot.database import get_db, TrackedWallet
from bot.trading.polymarket import PolymarketDataClient
from bot.utils.helpers import score_wallet, get_score_label
from bot.utils.logger import logger

settings = get_settings()


@dataclass
class WalletAnalysis:
    address: str
    win_rate: float
    total_trades: int
    total_profit_usd: float
    score: float
    score_label: str
    is_qualified: bool
    latest_trade: Optional[dict] = None
    disqualify_reason: str = ""


class InsiderScanner:
    """
    Détecte les wallets à haut win-rate (insiders potentiels).
    Logique:
      1. Charge les top traders via le leaderboard Polymarket
      2. Analyse leur historique de trades
      3. Score chaque wallet (win_rate, volume, profit)
      4. Persiste les wallets qualifiés en DB
      5. Détecte les nouveaux trades depuis la dernière analyse
    """

    def __init__(self, client: PolymarketDataClient):
        self.client = client
        self._known_trades: dict[str, set[str]] = {}  # wallet -> set(trade_ids)

    async def analyze_wallet(self, wallet_address: str) -> WalletAnalysis:
        """Analyse complète d'un wallet et retourne son score."""
        trades = await self.client.get_wallet_trades(wallet_address, limit=200)

        if not trades:
            return WalletAnalysis(
                address=wallet_address,
                win_rate=0, total_trades=0, total_profit_usd=0,
                score=0, score_label="🔴 D (Weak)",
                is_qualified=False,
                disqualify_reason="No trade history"
            )

        # Filtrer seulement les trades résolus (won/lost)
        resolved = [t for t in trades if t.get("type") in ("REDEEM", "SELL")]
        total = len(resolved)

        if total < settings.min_trades_count:
            return WalletAnalysis(
                address=wallet_address,
                win_rate=0, total_trades=total, total_profit_usd=0,
                score=0, score_label="🔴 D (Weak)",
                is_qualified=False,
                disqualify_reason=f"Not enough trades ({total} < {settings.min_trades_count})"
            )

        # Calcul win rate basé sur le P&L par trade
        profitable = sum(
            1 for t in resolved
            if float(t.get("usdcSize", 0)) > float(t.get("tradeSize", 0))
        )
        win_rate = profitable / total if total > 0 else 0

        # Profit total
        total_profit = sum(
            float(t.get("usdcSize", 0)) - float(t.get("tradeSize", 0))
            for t in resolved
        )

        score = score_wallet(win_rate, total, total_profit)
        label = get_score_label(score)
        qualified = win_rate >= settings.min_win_rate

        # Stocker les trade IDs connus
        self._known_trades[wallet_address] = {
            t.get("id", "") for t in trades
        }

        return WalletAnalysis(
            address=wallet_address,
            win_rate=win_rate,
            total_trades=total,
            total_profit_usd=total_profit,
            score=score,
            score_label=label,
            is_qualified=qualified,
            latest_trade=trades[0] if trades else None,
            disqualify_reason="" if qualified else f"Win rate too low ({win_rate:.0%})"
        )

    async def get_new_trades(self, wallet_address: str) -> list[dict]:
        """
        Retourne uniquement les trades NOUVEAUX depuis la dernière analyse.
        C'est ce qui déclenche le copy trading.
        """
        trades = await self.client.get_wallet_trades(wallet_address, limit=20)
        known = self._known_trades.get(wallet_address, set())

        new_trades = []
        for trade in trades:
            trade_id = trade.get("id", "")
            if trade_id and trade_id not in known:
                new_trades.append(trade)
                known.add(trade_id)

        self._known_trades[wallet_address] = known
        return new_trades

    async def refresh_tracked_wallets(self) -> list[WalletAnalysis]:
        """
        Scan global: met à jour tous les wallets suivis en DB.
        À appeler périodiquement (ex. toutes les heures).
        """
        logger.info("Starting full wallet refresh...")
        top_traders = await self.client.get_top_traders(limit=200)

        results = []
        tasks = [
            self.analyze_wallet(trader.get("proxyWalletAddress", ""))
            for trader in top_traders
            if trader.get("proxyWalletAddress")
        ]

        analyses = await asyncio.gather(*tasks, return_exceptions=True)

        with get_db() as db:
            for analysis in analyses:
                if isinstance(analysis, Exception):
                    logger.warning(f"Wallet analysis failed: {analysis}")
                    continue

                if not analysis.is_qualified:
                    continue

                # Upsert en DB
                wallet = db.get(TrackedWallet, analysis.address)
                if wallet is None:
                    wallet = TrackedWallet(address=analysis.address)
                    db.add(wallet)
                    logger.info(f"✨ New insider detected: {analysis.address[:8]}... {analysis.score_label}")

                wallet.win_rate = analysis.win_rate
                wallet.total_trades = analysis.total_trades
                wallet.total_profit_usd = analysis.total_profit_usd
                wallet.score = analysis.score
                wallet.is_active = True

                results.append(analysis)

        logger.info(f"Wallet refresh done. {len(results)} qualified wallets tracked.")
        return results
