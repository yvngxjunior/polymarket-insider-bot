"""
Unit tests — WalletScorer + MarketAnalyzer
Zero appels API: le LLMAgent est mocké ou désactivé.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.ai.scorer import WalletScore, WalletScorer, WalletTier
from bot.ai.market_analyzer import MarketAnalysis, MarketAnalyzer


# ===========================================================================
# WalletScorer
# ===========================================================================

@pytest.fixture
def scorer():
    return WalletScorer()


def test_elite_wallet(scorer):
    """Un wallet avec d'excellentes stats doit être tier ELITE."""
    result = scorer.score_wallet(
        address="0xElite",
        win_rate=0.85,
        total_trades=80,
        recent_win_rate=0.90,
        avg_bet_usdc=800.0,
        pnl_stddev=50.0,
    )
    assert isinstance(result, WalletScore)
    assert result.tier == WalletTier.ELITE
    assert result.score >= 0.80
    assert result.should_track is True


def test_skip_wallet(scorer):
    """Un wallet avec de mauvaises stats doit être tier SKIP."""
    result = scorer.score_wallet(
        address="0xBad",
        win_rate=0.40,
        total_trades=5,
        recent_win_rate=0.35,
        avg_bet_usdc=10.0,
        pnl_stddev=500.0,
    )
    assert result.tier == WalletTier.SKIP
    assert result.score < 0.50
    assert result.should_track is False


def test_score_clamped_between_0_and_1(scorer):
    """Le score composite doit toujours être entre 0.0 et 1.0."""
    for wr in [0.0, 0.5, 1.0]:
        result = scorer.score_wallet(
            address="0xTest",
            win_rate=wr,
            total_trades=100,
            recent_win_rate=wr,
            avg_bet_usdc=200.0,
        )
        assert 0.0 <= result.score <= 1.0


def test_zero_trades_gives_low_score(scorer):
    """Sans historique de trades, le score doit être très bas."""
    result = scorer.score_wallet(
        address="0xNew",
        win_rate=1.0,   # win rate parfait mais 0 trades
        total_trades=0,
        recent_win_rate=1.0,
        avg_bet_usdc=1000.0,
    )
    # score_a = 0 (0 trades) → score global forcément bas
    assert result.score_a == 0.0
    assert result.tier in (WalletTier.SKIP, WalletTier.WEAK)


def test_whale_bet_boosts_score_c(scorer):
    """Un gros parieur doit avoir un score_c élevé."""
    small = scorer.score_wallet("0xSmall", 0.7, 30, 0.7, avg_bet_usdc=20.0)
    big   = scorer.score_wallet("0xBig",   0.7, 30, 0.7, avg_bet_usdc=2000.0)
    assert big.score_c > small.score_c


def test_consistent_wallet_high_score_d(scorer):
    """Un wallet consistant (stddev=0) doit avoir score_d=1.0."""
    result = scorer.score_wallet(
        address="0xConsistent",
        win_rate=0.75,
        total_trades=50,
        recent_win_rate=0.75,
        avg_bet_usdc=200.0,
        pnl_stddev=0.0,
    )
    assert result.score_d == 1.0


def test_str_representation(scorer):
    """__str__ doit retourner une chaîne lisible avec le tier."""
    result = scorer.score_wallet("0xABC123", 0.75, 40, 0.78, 300.0)
    s = str(result)
    assert "0xABC123" in s
    assert result.tier.value in s


# ===========================================================================
# MarketAnalyzer
# ===========================================================================

def make_market(
    volume: float = 1000.0,
    bid: float = 0.40,
    ask: float = 0.43,
    end_date: str = "2026-03-15T00:00:00Z",
    question: str = "Will X happen?",
    condition_id: str = "cond_test",
) -> dict:
    return {
        "conditionId": condition_id,
        "question": question,
        "volume24hr": volume,
        "bestBid": bid,
        "bestAsk": ask,
        "endDate": end_date,
    }


@pytest.fixture
def analyzer_no_llm():
    """Analyzer avec LLM désactivé (is_enabled=False)."""
    llm = MagicMock()
    llm.is_enabled.return_value = False
    return MarketAnalyzer(llm_agent=llm)


@pytest.mark.asyncio
async def test_good_market_should_trade(analyzer_no_llm):
    """Un marché liquide, spread correct, prix normal → should_trade=True."""
    result = await analyzer_no_llm.analyze(make_market(), yes_price=0.42)
    assert isinstance(result, MarketAnalysis)
    assert result.should_trade is True
    assert result.reasons_skip == []


@pytest.mark.asyncio
async def test_low_volume_blocks_trade(analyzer_no_llm):
    """Volume 24h trop faible → should_trade=False."""
    result = await analyzer_no_llm.analyze(make_market(volume=50.0), yes_price=0.42)
    assert result.should_trade is False
    assert any("low_volume" in r for r in result.reasons_skip)


@pytest.mark.asyncio
async def test_price_too_high_blocks_trade(analyzer_no_llm):
    """Prix > 0.90 → should_trade=False."""
    result = await analyzer_no_llm.analyze(make_market(), yes_price=0.95)
    assert result.should_trade is False
    assert any("price_too_high" in r for r in result.reasons_skip)


@pytest.mark.asyncio
async def test_price_too_low_blocks_trade(analyzer_no_llm):
    """Prix < 0.05 → should_trade=False."""
    result = await analyzer_no_llm.analyze(make_market(), yes_price=0.02)
    assert result.should_trade is False
    assert any("price_too_low" in r for r in result.reasons_skip)


@pytest.mark.asyncio
async def test_llm_buy_no_blocks_trade():
    """Si LLM retourne BUY_NO, should_trade=False même si heuristiques OK."""
    from bot.ai.llm_agent import LLMSignal
    llm = MagicMock()
    llm.is_enabled.return_value = True
    llm.analyze_market = AsyncMock(return_value=LLMSignal(
        condition_id="cond_test",
        question="Will X?",
        current_price=0.42,
        recommendation="BUY_NO",
        confidence=0.85,
        fair_probability=0.20,
        reasoning="Overpriced based on news",
        mispricing_pct=0.22,
    ))
    analyzer = MarketAnalyzer(llm_agent=llm)
    result = await analyzer.analyze(make_market(), yes_price=0.42)
    assert result.should_trade is False
    assert any("LLM:BUY_NO" in r for r in result.reasons_skip)


@pytest.mark.asyncio
async def test_llm_buy_yes_boosts_confidence():
    """Si LLM retourne BUY_YES avec mispricing, confidence_boost > 0."""
    from bot.ai.llm_agent import LLMSignal
    llm = MagicMock()
    llm.is_enabled.return_value = True
    llm.analyze_market = AsyncMock(return_value=LLMSignal(
        condition_id="cond_test",
        question="Will X?",
        current_price=0.42,
        recommendation="BUY_YES",
        confidence=0.82,
        fair_probability=0.65,
        reasoning="Strong momentum",
        mispricing_pct=0.23,
    ))
    analyzer = MarketAnalyzer(llm_agent=llm)
    result = await analyzer.analyze(make_market(), yes_price=0.42)
    assert result.should_trade is True
    assert result.confidence_boost > 0.0
    assert result.llm_recommendation == "BUY_YES"
