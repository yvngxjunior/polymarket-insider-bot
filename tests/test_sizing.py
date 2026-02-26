"""
Unit tests — PositionSizer
"""
import pytest
from bot.config import get_settings
from bot.trading.sizing import PositionSizer

settings = get_settings()


@pytest.fixture
def s():
    return PositionSizer(capital_usdc=1000.0)


def test_basic_output(s):
    r = s.calculate(yes_price=0.50, conviction_score=0.75)
    assert r.amount_usdc >= settings.min_trade_usdc
    assert r.amount_usdc <= settings.max_trade_amount


def test_invalid_price_returns_min(s):
    r = s.calculate(yes_price=0.0, conviction_score=0.75)
    assert r.amount_usdc == settings.min_trade_usdc


def test_higher_conviction_bigger_size(s):
    low  = s.calculate(yes_price=0.50, conviction_score=0.52)
    high = s.calculate(yes_price=0.50, conviction_score=0.90)
    assert low.amount_usdc <= high.amount_usdc


def test_kelly_fraction_non_negative(s):
    r = s.calculate(yes_price=0.50, conviction_score=0.75)
    assert r.kelly_fraction >= 0


def test_pct_of_capital_valid(s):
    r = s.calculate(yes_price=0.30, conviction_score=0.80)
    assert 0 <= r.pct_of_capital <= 1.0


def test_source_amount_in_rationale(s):
    r = s.calculate(yes_price=0.50, conviction_score=0.75, source_amount=500.0)
    assert "ratio" in r.rationale


def test_update_capital(s):
    s.update_capital(2000.0)
    assert s._capital == 2000.0
