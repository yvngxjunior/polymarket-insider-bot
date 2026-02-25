"""
Backtest Engine — PolyInsider Bot v2.2
======================================
Rejoue l'historique des trades d'un ensemble de wallets insiders
at travers la pile de décision du bot (ConvictionFilter + RiskManager)
pour valider la stratégie AVANT de risquer du capital réel.

Fonctionnement:
  1. Récupère les trades historiques de chaque wallet via PolymarketDataClient
  2. Pour chaque trade REDEEM/SELL (outcome connu), simule la décision du bot:
     - Aurait-on passé le ConvictionFilter ?
     - Quel montant Kelly aurait-on misé ?
     - Le trade était-il gagnant ? (usdcSize > tradeSize)
  3. Calcule les métriques: P&L simulé, win rate, Sharpe, max drawdown,
     meilleur/pire trade, détails par wallet

Usage CLI:
  python -m bot.analytics.backtest --wallets 0xABC,0xDEF --capital 500

Usage Python:
  from bot.analytics.backtest import BacktestEngine
  engine = BacktestEngine(capital=500)
  result = await engine.run(wallets=["0xABC", "0xDEF"])
  print(result.summary())
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
from dataclasses import dataclass, field

from bot.trading.filters import ConvictionFilter
from bot.trading.sizing import PositionSizer
from bot.utils.logger import logger


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class BacktestTrade:
    """Un trade simulé pendant le backtest."""
    wallet: str
    token_id: str
    side: str
    entry_price: float
    source_amount: float
    simulated_amount: float       # montant Kelly que le bot aurait misé
    pnl: float                    # P&L réalisé sur ce trade
    won: bool                     # True si trade profitable
    filter_reason: str = ""       # raison si filtré / "ok" si exécuté
    market_question: str = ""


@dataclass
class WalletBacktestResult:
    """Résultat backtest pour un wallet."""
    address: str
    trades_total: int = 0
    trades_taken: int = 0
    trades_won: int = 0
    pnl: float = 0.0
    win_rate: float = 0.0


@dataclass
class BacktestResult:
    """
    Résultat global du backtest.

    Attributs:
        trades:           liste de tous les BacktestTrade simulés
        initial_capital:  capital de départ
        final_capital:    capital après simulation
        total_pnl:        P&L total en USDC
        win_rate:         taux de trades gagnants (parmi ceux exécutés)
        sharpe:           Sharpe ratio sur les P&L individuels
        max_drawdown:     drawdown maximal observé pendant la simulation
        per_wallet:       dict address → WalletBacktestResult
    """
    trades: list[BacktestTrade] = field(default_factory=list)
    initial_capital: float = 500.0
    final_capital: float = 500.0
    total_pnl: float = 0.0
    win_rate: float = 0.0
    sharpe: float = 0.0
    max_drawdown: float = 0.0
    per_wallet: dict[str, WalletBacktestResult] = field(default_factory=dict)

    def summary(self) -> str:
        """Retourne un résumé texte lisible."""
        executed = [t for t in self.trades if t.filter_reason == "ok"]
        filtered = len(self.trades) - len(executed)
        top_wallets = sorted(
            self.per_wallet.values(), key=lambda w: w.pnl, reverse=True
        )[:3]

        lines = [
            "=" * 55,
            "  BACKTEST RESULTS — PolyInsider Bot",
            "=" * 55,
            f"  Capital:      ${self.initial_capital:.2f} → ${self.final_capital:.2f}",
            f"  P&L total:    ${self.total_pnl:+.2f} USDC",
            f"  Win rate:     {self.win_rate:.1%}",
            f"  Sharpe:       {self.sharpe:.2f}",
            f"  Max drawdown: {self.max_drawdown:.1%}",
            f"  Trades taken: {len(executed)} / {len(self.trades)} ({filtered} filtered)",
            "-" * 55,
            "  Top wallets by P&L:",
        ]
        for w in top_wallets:
            lines.append(
                f"    {w.address[:10]}... "
                f"P&L=${w.pnl:+.2f}  WR={w.win_rate:.0%}  "
                f"trades={w.trades_taken}/{w.trades_total}"
            )
        lines.append("=" * 55)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class BacktestEngine:
    """
    Moteur de backtest: simule les décisions du bot sur l'historique.

    Args:
        capital:            Capital initial en USDC (défaut: 500)
        wallet_score:       Win rate supposé des wallets (défaut: 0.70)
        consecutive_losses: Pertes consécutives supposées au début (défaut: 0)
        client:             PolymarketDataClient (injecté ou créé automatiquement)
    """

    def __init__(
        self,
        capital: float = 500.0,
        wallet_score: float = 0.70,
        consecutive_losses: int = 0,
        client=None,
    ) -> None:
        self.initial_capital = capital
        self.wallet_score = wallet_score
        self.consecutive_losses = consecutive_losses
        self._filter = ConvictionFilter()
        self._sizer = PositionSizer(capital_usdc=capital)
        self._client = client

    # ------------------------------------------------------------------
    # Point d'entrée principal
    # ------------------------------------------------------------------

    async def run(
        self,
        wallets: list[str],
        limit_per_wallet: int = 300,
    ) -> BacktestResult:
        """
        Lance le backtest sur une liste de wallets.

        Args:
            wallets:           liste d'adresses à backtester
            limit_per_wallet:  nombre max de trades historiques par wallet

        Returns:
            BacktestResult avec toutes les métriques
        """
        client = await self._get_client()
        all_trades: list[BacktestTrade] = []
        per_wallet: dict[str, WalletBacktestResult] = {}

        for address in wallets:
            logger.info(f"[BACKTEST] Fetching {address[:10]}... (limit={limit_per_wallet})")
            raw_trades = await client.get_wallet_trades(address, limit=limit_per_wallet)
            w_result = WalletBacktestResult(address=address)
            wallet_trades = self._simulate_wallet(
                address=address,
                raw_trades=raw_trades,
                w_result=w_result,
            )
            all_trades.extend(wallet_trades)
            per_wallet[address] = w_result
            logger.info(
                f"[BACKTEST] {address[:10]}... "
                f"{w_result.trades_taken}/{w_result.trades_total} trades taken | "
                f"P&L=${w_result.pnl:+.2f}  WR={w_result.win_rate:.0%}"
            )

        return self._compute_result(all_trades, per_wallet)

    # ------------------------------------------------------------------
    # Simulation d'un wallet
    # ------------------------------------------------------------------

    def _simulate_wallet(
        self,
        address: str,
        raw_trades: list[dict],
        w_result: WalletBacktestResult,
    ) -> list[BacktestTrade]:
        """Rejoue les trades d'un wallet et retourne la liste des BacktestTrade."""
        resolved = [
            t for t in raw_trades
            if t.get("type") in ("REDEEM", "SELL")
            and float(t.get("price", 0)) > 0
        ]
        w_result.trades_total = len(resolved)
        simulated: list[BacktestTrade] = []

        for trade in resolved:
            bt = self._simulate_trade(address, trade)
            simulated.append(bt)

            if bt.filter_reason == "ok":
                w_result.trades_taken += 1
                w_result.pnl += bt.pnl
                if bt.won:
                    w_result.trades_won += 1

        if w_result.trades_taken > 0:
            w_result.win_rate = w_result.trades_won / w_result.trades_taken

        return simulated

    def _simulate_trade(self, wallet: str, raw: dict) -> BacktestTrade:
        """Simule la décision du bot sur un trade historique."""
        price        = float(raw.get("price", 0))
        usdc_size    = float(raw.get("usdcSize", 0))
        trade_size   = float(raw.get("tradeSize", 0))
        side         = raw.get("side", "BUY").upper()
        token_id     = raw.get("asset", "")
        condition_id = raw.get("conditionId", "")
        question     = raw.get("title", "") or ""

        f = self._filter.evaluate(
            source_amount=usdc_size,
            price=price,
            wallet_score=self.wallet_score,
            market_id=condition_id,
            consecutive_losses=self.consecutive_losses,
        )

        if not f.passed:
            return BacktestTrade(
                wallet=wallet, token_id=token_id, side=side,
                entry_price=price, source_amount=usdc_size,
                simulated_amount=0.0, pnl=0.0, won=False,
                filter_reason=f.reason,
                market_question=question,
            )

        size = self._sizer.calculate(
            yes_price=price,
            conviction_score=f.score,
            source_amount=usdc_size,
        )

        won = usdc_size > trade_size
        if won:
            profit_ratio = (usdc_size - trade_size) / trade_size if trade_size > 0 else 0
            pnl = size.amount_usdc * profit_ratio
        else:
            pnl = -size.amount_usdc

        return BacktestTrade(
            wallet=wallet, token_id=token_id, side=side,
            entry_price=price, source_amount=usdc_size,
            simulated_amount=size.amount_usdc,
            pnl=round(pnl, 4),
            won=won,
            filter_reason="ok",
            market_question=question,
        )

    # ------------------------------------------------------------------
    # Calcul des métriques globales
    # ------------------------------------------------------------------

    def _compute_result(
        self,
        trades: list[BacktestTrade],
        per_wallet: dict[str, WalletBacktestResult],
    ) -> BacktestResult:
        """Calcule toutes les métriques globales depuis la liste de trades simulés."""
        executed = [t for t in trades if t.filter_reason == "ok"]

        if not executed:
            return BacktestResult(
                trades=trades,
                initial_capital=self.initial_capital,
                final_capital=self.initial_capital,
                per_wallet=per_wallet,
            )

        total_pnl = sum(t.pnl for t in executed)
        final_capital = self.initial_capital + total_pnl
        wins = [t for t in executed if t.won]
        win_rate = len(wins) / len(executed) if executed else 0.0
        sharpe = self._sharpe(executed)
        max_dd = self._max_drawdown(executed, self.initial_capital)

        return BacktestResult(
            trades=trades,
            initial_capital=self.initial_capital,
            final_capital=round(final_capital, 2),
            total_pnl=round(total_pnl, 2),
            win_rate=round(win_rate, 4),
            sharpe=round(sharpe, 3),
            max_drawdown=round(max_dd, 4),
            per_wallet=per_wallet,
        )

    # ------------------------------------------------------------------
    # Métriques
    # ------------------------------------------------------------------

    @staticmethod
    def _sharpe(trades: list[BacktestTrade], risk_free: float = 0.0) -> float:
        """Sharpe ratio simplifié (basé sur les P&L par trade)."""
        pnls = [t.pnl for t in trades]
        if len(pnls) < 2:
            return 0.0
        avg = statistics.mean(pnls) - risk_free
        std = statistics.stdev(pnls)
        return avg / std if std > 0 else 0.0

    @staticmethod
    def _max_drawdown(trades: list[BacktestTrade], initial_capital: float) -> float:
        """Max drawdown en % depuis le pic de capital."""
        capital = initial_capital
        peak = initial_capital
        max_dd = 0.0
        for t in trades:
            capital += t.pnl
            if capital > peak:
                peak = capital
            if peak > 0:
                dd = (peak - capital) / peak
                max_dd = max(max_dd, dd)
        return max_dd

    # ------------------------------------------------------------------
    # Client lazy
    # ------------------------------------------------------------------

    async def _get_client(self):
        if self._client is None:
            from bot.trading.polymarket import PolymarketDataClient
            self._client = PolymarketDataClient()
        return self._client


# ---------------------------------------------------------------------------
# CLI runner
# ---------------------------------------------------------------------------

async def _cli_main(wallets: list[str], capital: float, score: float) -> None:
    from bot.trading.polymarket import PolymarketDataClient
    client = PolymarketDataClient()
    try:
        engine = BacktestEngine(capital=capital, wallet_score=score, client=client)
        result = await engine.run(wallets=wallets)
        print(result.summary())

        if result.per_wallet:
            print("\nDétails par wallet:")
            for addr, w in sorted(
                result.per_wallet.items(), key=lambda x: x[1].pnl, reverse=True
            ):
                print(
                    f"  {addr[:12]}...  "
                    f"P&L={w.pnl:+.2f}$  "
                    f"WR={w.win_rate:.0%}  "
                    f"({w.trades_taken}/{w.trades_total} trades)"
                )
    finally:
        await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PolyInsider Backtest")
    parser.add_argument(
        "--wallets", required=True,
        help="Adresses séparées par virgule. Ex: 0xABC,0xDEF"
    )
    parser.add_argument(
        "--capital", type=float, default=500.0,
        help="Capital initial en USDC (défaut: 500)"
    )
    parser.add_argument(
        "--score", type=float, default=0.70,
        help="Win rate supposé des wallets (0.0-1.0, défaut: 0.70)"
    )
    args = parser.parse_args()
    wallet_list = [w.strip() for w in args.wallets.split(",") if w.strip()]
    asyncio.run(_cli_main(wallet_list, args.capital, args.score))
