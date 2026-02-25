"""
Unit tests — BacktestEngine

Tous les tests sont synchrones (pas besoin de l'API Polymarket):
les trades historiques sont injectés directement via un mock client.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from bot.analytics.backtest import BacktestEngine, BacktestResult, BacktestTrade


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_trade(
    price: float = 0.40,
    usdc_size: float = 100.0,
    trade_size: float = 60.0,     # usdc_size > trade_size → gagnant
    side: str = "BUY",
    type_: str = "REDEEM",
    condition_id: str = "cond_001",
) -> dict:
    """Crée un dict de trade historique Polymarket."""
    return {
        "type": type_,
        "price": price,
        "usdcSize": usdc_size,
        "tradeSize": trade_size,
        "side": side,
        "asset": "tok_abc",
        "conditionId": condition_id,
        "title": "Will X happen?",
    }


def mock_client(trades_per_wallet: list[dict]) -> AsyncMock:
    """Crée un client mock qui retourne la même liste pour chaque wallet."""
    client = AsyncMock()
    client.get_wallet_trades = AsyncMock(return_value=trades_per_wallet)
    return client


@pytest.fixture
def engine_small():
    """Engine avec capital 1000 USDC et 3 trades injectés."""
    trades = [
        make_trade(price=0.40, usdc_size=200.0, trade_size=100.0),  # gagnant
        make_trade(price=0.35, usdc_size=150.0, trade_size=90.0),   # gagnant
        make_trade(price=0.45, usdc_size=180.0, trade_size=200.0),  # perdant
    ]
    client = mock_client(trades)
    return BacktestEngine(capital=1000.0, wallet_score=0.75, client=client)


# ---------------------------------------------------------------------------
# Tests de base
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_returns_backtest_result(engine_small):
    """run() doit retourner un BacktestResult."""
    result = await engine_small.run(wallets=["0xWallet1"])
    assert isinstance(result, BacktestResult)


@pytest.mark.asyncio
async def test_trades_are_backtest_trade_instances(engine_small):
    """
    Chaque élément de result.trades doit être une instance de BacktestTrade.
    Vérifie que le moteur retourne bien le bon type et que les champs clés
    (wallet, pnl, won, filter_reason) sont présents et correctement typés.
    """
    result = await engine_small.run(wallets=["0xWallet1"])
    assert len(result.trades) > 0
    for trade in result.trades:
        assert isinstance(trade, BacktestTrade)
        assert isinstance(trade.wallet, str)
        assert isinstance(trade.pnl, float)
        assert isinstance(trade.won, bool)
        assert isinstance(trade.filter_reason, str)
        assert isinstance(trade.simulated_amount, float)


@pytest.mark.asyncio
async def test_trades_count_matches_resolved(engine_small):
    """Le nombre de trades simulés doit correspondre aux trades REDEEM/SELL injectés."""
    result = await engine_small.run(wallets=["0xWallet1"])
    assert len(result.trades) == 3


@pytest.mark.asyncio
async def test_winning_trades_increase_pnl(engine_small):
    """Les trades gagnants doivent produire un P&L positif global."""
    result = await engine_small.run(wallets=["0xWallet1"])
    # 2 gagnants, 1 perdant → P&L global doit être positif
    assert result.total_pnl > 0


@pytest.mark.asyncio
async def test_final_capital_equals_initial_plus_pnl(engine_small):
    """final_capital == initial_capital + total_pnl."""
    result = await engine_small.run(wallets=["0xWallet1"])
    assert abs(result.final_capital - (result.initial_capital + result.total_pnl)) < 0.01


@pytest.mark.asyncio
async def test_win_rate_between_0_and_1(engine_small):
    """Le win rate doit être un float entre 0.0 et 1.0."""
    result = await engine_small.run(wallets=["0xWallet1"])
    assert 0.0 <= result.win_rate <= 1.0


@pytest.mark.asyncio
async def test_max_drawdown_non_negative(engine_small):
    """Le max drawdown doit être >= 0."""
    result = await engine_small.run(wallets=["0xWallet1"])
    assert result.max_drawdown >= 0.0


@pytest.mark.asyncio
async def test_per_wallet_populated(engine_small):
    """per_wallet doit contenir une entrée pour chaque wallet passé."""
    result = await engine_small.run(wallets=["0xWallet1", "0xWallet2"])
    assert "0xWallet1" in result.per_wallet
    assert "0xWallet2" in result.per_wallet


@pytest.mark.asyncio
async def test_executed_trades_have_positive_simulated_amount(engine_small):
    """Les trades exécutés (filter_reason='ok') doivent avoir un montant Kelly > 0."""
    result = await engine_small.run(wallets=["0xWallet1"])
    executed = [t for t in result.trades if t.filter_reason == "ok"]
    assert all(isinstance(t, BacktestTrade) for t in executed)
    assert all(t.simulated_amount > 0 for t in executed)


# ---------------------------------------------------------------------------
# Tests filtre
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_small_bets_are_filtered_out():
    """Les trades avec bet source trop petit doivent être filtrés (filter_reason != 'ok')."""
    trades = [make_trade(usdc_size=5.0, trade_size=3.0)]  # < 50 USDC min
    engine = BacktestEngine(
        capital=500.0, wallet_score=0.75, client=mock_client(trades)
    )
    result = await engine.run(wallets=["0xWallet1"])
    assert all(isinstance(t, BacktestTrade) for t in result.trades)
    assert all(t.filter_reason != "ok" for t in result.trades)


@pytest.mark.asyncio
async def test_non_resolved_trades_excluded():
    """Les trades de type BUY (non résolus) ne doivent pas être simulés."""
    trades = [
        make_trade(type_="BUY"),    # pas REDEEM ni SELL → ignoré
        make_trade(type_="REDEEM"),
    ]
    engine = BacktestEngine(
        capital=500.0, wallet_score=0.75, client=mock_client(trades)
    )
    result = await engine.run(wallets=["0xWallet1"])
    assert len(result.trades) == 1
    assert isinstance(result.trades[0], BacktestTrade)


@pytest.mark.asyncio
async def test_losing_streak_filters_all_trades():
    """
    Avec consecutive_losses=3 (= MAX_CONSECUTIVE_LOSSES),
    tous les trades doivent être filtrés et le P&L = 0.
    """
    trades = [
        make_trade(usdc_size=200.0, trade_size=100.0),
        make_trade(usdc_size=300.0, trade_size=150.0),
    ]
    engine = BacktestEngine(
        capital=500.0,
        wallet_score=0.75,
        consecutive_losses=3,
        client=mock_client(trades),
    )
    result = await engine.run(wallets=["0xWallet1"])
    assert all(isinstance(t, BacktestTrade) for t in result.trades)
    assert all(t.filter_reason != "ok" for t in result.trades)
    assert result.total_pnl == 0.0


# ---------------------------------------------------------------------------
# Test summary
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_summary_returns_string(engine_small):
    """summary() doit retourner une chaîne non vide avec les sections attendues."""
    result = await engine_small.run(wallets=["0xWallet1"])
    s = result.summary()
    assert isinstance(s, str)
    assert "BACKTEST" in s
    assert "P&L" in s
