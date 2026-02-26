"""
Unit tests — ConvictionFilter
Couvre tous les checks individuels + le scoring global.
v2.3: tests pour entry_timing_score (check #6)
"""
import pytest
from bot.trading.filters import ConvictionFilter


@pytest.fixture
def f():
    return ConvictionFilter()


# ------------------------------------------------------------------
# Bet size
# ------------------------------------------------------------------

def test_bet_below_min_fails(f):
    r = f.evaluate(source_amount=10.0, price=0.5, wallet_score=0.8)
    assert not r.passed
    assert "Source bet" in r.reason


def test_bet_at_min_passes(f):
    r = f.evaluate(source_amount=50.0, price=0.5, wallet_score=0.8)
    assert r.passed


# ------------------------------------------------------------------
# Price
# ------------------------------------------------------------------

def test_price_too_high_fails(f):
    r = f.evaluate(source_amount=100.0, price=0.95, wallet_score=0.8)
    assert not r.passed
    assert "Price" in r.reason


def test_price_too_low_fails(f):
    r = f.evaluate(source_amount=100.0, price=0.02, wallet_score=0.8)
    assert not r.passed


def test_price_valid_passes(f):
    r = f.evaluate(source_amount=100.0, price=0.50, wallet_score=0.8)
    assert r.passed


# ------------------------------------------------------------------
# Wallet score
# ------------------------------------------------------------------

def test_low_wallet_score_fails(f):
    r = f.evaluate(source_amount=100.0, price=0.5, wallet_score=0.40)
    assert not r.passed
    assert "score" in r.reason.lower()


# ------------------------------------------------------------------
# Losing streak
# ------------------------------------------------------------------

def test_losing_streak_skip(f):
    r = f.evaluate(
        source_amount=100.0, price=0.5, wallet_score=0.8,
        consecutive_losses=3
    )
    assert not r.passed
    assert "streak" in r.reason.lower()


def test_losing_streak_below_max_passes(f):
    r = f.evaluate(
        source_amount=100.0, price=0.5, wallet_score=0.8,
        consecutive_losses=2
    )
    assert r.passed
    # Léger malus de score attendu
    assert r.score < 1.0


# ------------------------------------------------------------------
# Entry timing (NEW v2.3)
# ------------------------------------------------------------------

def test_late_entry_poor_timing_fails(f):
    """Prix > 0.70 ET timing_score < 0.30 → SKIP."""
    r = f.evaluate(
        source_amount=100.0, price=0.75, wallet_score=0.8,
        entry_timing_score=0.20,
    )
    assert not r.passed
    assert "Late entry" in r.reason


def test_late_price_good_timing_passes(f):
    """Prix > 0.70 mais timing_score > 0.30 → passe avec malus."""
    r = f.evaluate(
        source_amount=100.0, price=0.75, wallet_score=0.8,
        entry_timing_score=0.70,
    )
    assert r.passed
    # Score réduit à cause du prix élevé
    assert r.score < 0.75


def test_normal_price_good_timing_full_score(f):
    """Prix normal + bon timing → passe sans malus de timing."""
    r = f.evaluate(
        source_amount=100.0, price=0.45, wallet_score=0.8,
        entry_timing_score=0.80,
    )
    assert r.passed


def test_default_timing_score_passes(f):
    """Sans entry_timing_score (défaut 0.5) → passe pour un prix normal."""
    r = f.evaluate(source_amount=100.0, price=0.45, wallet_score=0.8)
    assert r.passed


# ------------------------------------------------------------------
# Score global
# ------------------------------------------------------------------

def test_all_pass_score_between_0_and_1(f):
    r = f.evaluate(
        source_amount=200.0, price=0.45, wallet_score=0.80,
        entry_timing_score=0.70,
    )
    assert r.passed
    assert 0.0 < r.score <= 1.0


def test_score_higher_with_better_timing(f):
    """Un meilleur timing doit donner un score global plus élevé."""
    r_low  = f.evaluate(source_amount=200.0, price=0.45, wallet_score=0.80, entry_timing_score=0.30)
    r_high = f.evaluate(source_amount=200.0, price=0.45, wallet_score=0.80, entry_timing_score=0.90)
    assert r_high.score > r_low.score
