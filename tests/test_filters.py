"""
Unit tests — ConvictionFilter
"""
import pytest
from bot.trading.filters import ConvictionFilter


@pytest.fixture
def f():
    return ConvictionFilter()


def test_bet_too_small(f):
    r = f.evaluate(source_amount=10.0, price=0.50, wallet_score=0.80)
    assert not r.passed
    assert "min" in r.reason.lower()


def test_bet_ok(f):
    r = f.evaluate(source_amount=200.0, price=0.50, wallet_score=0.80)
    assert r.passed


def test_price_too_high(f):
    r = f.evaluate(source_amount=200.0, price=0.95, wallet_score=0.80)
    assert not r.passed
    assert "max" in r.reason.lower()


def test_price_too_low(f):
    r = f.evaluate(source_amount=200.0, price=0.01, wallet_score=0.80)
    assert not r.passed
    assert "min" in r.reason.lower()


def test_wallet_score_too_low(f):
    r = f.evaluate(source_amount=200.0, price=0.50, wallet_score=0.40)
    assert not r.passed
    assert "score" in r.reason.lower()


def test_all_pass_returns_score(f):
    r = f.evaluate(source_amount=300.0, price=0.50, wallet_score=0.80)
    assert r.passed
    assert 0 < r.score <= 1.0


def test_rate_limit_blocks_4th_copy(f):
    for _ in range(3):
        f.evaluate(source_amount=300.0, price=0.50, wallet_score=0.80, market_id="mkt_x")
    r = f.evaluate(source_amount=300.0, price=0.50, wallet_score=0.80, market_id="mkt_x")
    assert not r.passed
    assert "rate" in r.reason.lower()


def test_different_markets_no_rate_limit(f):
    for i in range(6):
        r = f.evaluate(source_amount=300.0, price=0.50, wallet_score=0.80, market_id=f"mkt_{i}")
        assert r.passed
