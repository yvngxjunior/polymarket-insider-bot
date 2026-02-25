"""
Unit tests — ConvictionFilter
"""
import pytest
from bot.trading.filters import ConvictionFilter


@pytest.fixture
def f():
    return ConvictionFilter()


# ------------------------------------------------------------------
# Tests existants
# ------------------------------------------------------------------

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


# ------------------------------------------------------------------
# Nouveaux tests — Losing streak protection
# ------------------------------------------------------------------

def test_no_losing_streak_passes(f):
    """0 pertes consécutives — doit passer sans malus."""
    r = f.evaluate(
        source_amount=200.0, price=0.50,
        wallet_score=0.80, consecutive_losses=0,
    )
    assert r.passed
    assert r.score == pytest.approx(1.0, abs=0.5)  # score complet, pas de malus


def test_small_losing_streak_passes_with_penalty(f):
    """2 pertes consécutives — doit passer MAIS avec un score légèrement réduit."""
    r_clean   = f.evaluate(source_amount=200.0, price=0.50, wallet_score=0.80, consecutive_losses=0)
    r_penalty = f.evaluate(source_amount=200.0, price=0.50, wallet_score=0.80, consecutive_losses=2)
    assert r_penalty.passed
    assert r_penalty.score < r_clean.score  # score réduit mais toujours valide


def test_losing_streak_blocks_at_threshold(f):
    """3 pertes consécutives (= MAX_CONSECUTIVE_LOSSES) — doit être bloqué."""
    r = f.evaluate(
        source_amount=200.0, price=0.50,
        wallet_score=0.80, consecutive_losses=3,
    )
    assert not r.passed
    assert "losing streak" in r.reason.lower()


def test_heavy_losing_streak_blocked(f):
    """5 pertes consécutives — doit aussi être bloqué."""
    r = f.evaluate(
        source_amount=200.0, price=0.50,
        wallet_score=0.80, consecutive_losses=5,
    )
    assert not r.passed
    assert "losing streak" in r.reason.lower()


def test_losing_streak_check_runs_first(f):
    """
    Le check losing streak doit s'exécuter en PREMIER (fast-fail).
    Même si le bet est trop petit, la raison retournée doit être 'losing streak'.
    """
    r = f.evaluate(
        source_amount=5.0,   # trop petit (< 50 USDC)
        price=0.50,
        wallet_score=0.80,
        consecutive_losses=4,  # losing streak — doit être testé en premier
    )
    assert not r.passed
    assert "losing streak" in r.reason.lower()
