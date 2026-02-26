"""
Unit tests — RiskManager
"""
import pytest
from bot.config import get_settings
from bot.trading.risk import RiskManager

settings = get_settings()


@pytest.fixture
def rm():
    return RiskManager(initial_capital=500.0)


def test_normal_trade_approved(rm):
    d = rm.evaluate(token_id="tok_1", price=0.40, source_amount=50.0)
    assert d.approved
    assert d.amount_usdc > 0


def test_price_too_high_rejected(rm):
    d = rm.evaluate(token_id="tok_2", price=0.95, source_amount=50.0)
    assert not d.approved


def test_price_too_low_rejected(rm):
    d = rm.evaluate(token_id="tok_3", price=0.02, source_amount=50.0)
    assert not d.approved


def test_duplicate_rejected(rm):
    rm.register_position("tok_4")
    d = rm.evaluate(token_id="tok_4", price=0.50, source_amount=50.0)
    assert not d.approved


def test_max_positions_hit(rm):
    """Vérifie que MAX_POSITIONS bloque bien les nouveaux trades.
    Utilise settings.max_positions (configurable via .env MAX_POSITIONS).
    """
    for i in range(settings.max_positions):
        rm.register_position(f"tok_{i}")
    d = rm.evaluate(token_id="new_tok", price=0.50, source_amount=50.0)
    assert not d.approved


def test_release_updates_capital(rm):
    rm.register_position("tok_x")
    rm.release_position("tok_x", pnl=10.0)
    assert rm.portfolio.total_capital == 510.0


def test_kelly_fraction_positive(rm):
    d = rm.evaluate(token_id="tok_k", price=0.50, source_amount=50.0, wallet_win_rate=0.75)
    assert d.kelly_fraction >= 0


def test_convergence_boost_increases_size(rm):
    d1 = rm.evaluate(token_id="tok_n", price=0.50, source_amount=50.0)
    rm2 = RiskManager(initial_capital=500.0)
    d2 = rm2.evaluate(token_id="tok_b", price=0.50, source_amount=50.0, is_convergence_signal=True)
    assert d2.amount_usdc >= d1.amount_usdc
