"""
Market Analyzer — PolyInsider Bot
===================================
Analyse un marché AVANT d'exécuter un trade copié.
Combine heuristiques rapides (sans LLM) + analyse LLM optionnelle (GPT-4o-mini).

Heuristiques (toujours actives, gratuites):
  - Liquidité dynamique: volume24h >= trade_amount * LIQUIDITY_RATIO
    (adapté à la taille du trade, pas de seuil fixe codé en dur)
  - Spread: écart bid/ask pas trop large (slippage)
  - Clou du marché: end_date pas trop loin (capital immobilisé)
  - Prix: ni trop proche de 0 ni de 1 (peu de valeur espérée)

LLM (optionnel, nécessite LLM_ENABLED=true + OPENAI_API_KEY):
  - Demande à GPT-4o-mini si le marché est mispricé
  - Retourne un score de confiance supplémentaire

Usage:
  analyzer = MarketAnalyzer()
  result = await analyzer.analyze(market_data, yes_price=0.42, trade_amount=50.0)
  if result.should_trade:
      ...  # exécuter le trade
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from bot.ai.llm_agent import LLMAgent
from bot.utils.logger import logger


@dataclass
class MarketAnalysis:
    """Résultat de l'analyse d'un marché."""
    condition_id: str
    question: str
    yes_price: float
    should_trade: bool
    confidence_boost: float
    reasons_skip: list[str] = field(default_factory=list)
    llm_recommendation: str = "HOLD"
    llm_fair_probability: float = 0.0
    llm_reasoning: str = ""

    def __str__(self) -> str:
        status = "✅ TRADE" if self.should_trade else "⛔ SKIP"
        reasons = f" | skip: {', '.join(self.reasons_skip)}" if self.reasons_skip else ""
        llm_info = (
            f" | LLM={self.llm_recommendation} conf_boost={self.confidence_boost:+.2f}"
            if self.llm_recommendation != "HOLD"
            else ""
        )
        return f"{status} '{self.question[:50]}...'{reasons}{llm_info}"


class MarketAnalyzer:
    """
    Analyse pré-trade combinée: heuristiques + LLM optionnel.

    Args:
        liquidity_ratio:    volume24h minimum = trade_amount * ratio (défaut: 10x)
        min_volume_floor:   plancher absolu de volume même pour de petits trades (défaut: 200 USDC)
        max_spread_pct:     spread bid/ask max en % (défaut: 10%)
        max_days_to_close:  nombre max de jours avant clôture du marché (défaut: 30)
        min_price:          prix YES minimum acceptable (défaut: 0.05)
        max_price:          prix YES maximum acceptable (défaut: 0.90)
        llm_agent:          LLMAgent injecté (créé automatiquement sinon)
    """

    LIQUIDITY_RATIO = 10.0   # volume24h doit être >= trade_amount * 10
    MIN_VOLUME_FLOOR = 200.0  # plancher absolu (pour les très petits trades)

    def __init__(
        self,
        liquidity_ratio: float = 10.0,
        min_volume_floor: float = 200.0,
        max_spread_pct: float = 0.10,
        max_days_to_close: int = 30,
        min_price: float = 0.05,
        max_price: float = 0.90,
        llm_agent: LLMAgent | None = None,
    ) -> None:
        self.liquidity_ratio   = liquidity_ratio
        self.min_volume_floor  = min_volume_floor
        self.max_spread_pct    = max_spread_pct
        self.max_days_to_close = max_days_to_close
        self.min_price         = min_price
        self.max_price         = max_price
        self._llm = llm_agent or LLMAgent()

    # ------------------------------------------------------------------
    # Point d'entrée principal
    # ------------------------------------------------------------------

    async def analyze(
        self,
        market: dict,
        yes_price: float,
        trade_amount: float = 0.0,
    ) -> MarketAnalysis:
        """
        Analyse complète d'un marché.

        Args:
            market:       dict marché Polymarket (Gamma API format)
            yes_price:    prix actuel du token YES (0.0-1.0)
            trade_amount: montant qu'on va investir en USDC (pour la liquidité dynamique)

        Returns:
            MarketAnalysis avec should_trade + détails
        """
        condition_id = market.get("conditionId", "")
        question     = market.get("question", "")
        skip_reasons: list[str] = []

        # —— Heuristiques rapides (sans LLM) ———————————————————————
        self._check_volume(market, skip_reasons, trade_amount)
        self._check_spread(market, skip_reasons)
        self._check_end_date(market, skip_reasons)
        self._check_price(yes_price, skip_reasons)

        if skip_reasons:
            return MarketAnalysis(
                condition_id=condition_id,
                question=question,
                yes_price=yes_price,
                should_trade=False,
                confidence_boost=0.0,
                reasons_skip=skip_reasons,
            )

        # —— Analyse LLM (optionnelle) ———————————————————————————
        llm_rec = "HOLD"
        llm_fair = 0.0
        llm_reason = ""
        confidence_boost = 0.0

        if self._llm.is_enabled():
            try:
                signal = await self._llm.analyze_market(
                    condition_id=condition_id,
                    question=question,
                    yes_price=yes_price,
                )
                if signal:
                    llm_rec    = signal.recommendation
                    llm_fair   = signal.fair_probability
                    llm_reason = signal.reasoning
                    confidence_boost = min(signal.mispricing_pct * 2.0, 0.20)
                    if llm_rec == "BUY_NO":
                        skip_reasons.append(f"LLM:{llm_rec} fair={llm_fair:.0%}")
            except Exception as e:
                logger.warning(f"[ANALYZER] LLM error (ignored): {e}")

        should_trade = len(skip_reasons) == 0
        logger.debug(
            f"[ANALYZER] {'TRADE' if should_trade else 'SKIP'} "
            f"'{question[:40]}' price={yes_price:.0%} "
            f"llm={llm_rec} boost={confidence_boost:+.2f}"
        )

        return MarketAnalysis(
            condition_id=condition_id,
            question=question,
            yes_price=yes_price,
            should_trade=should_trade,
            confidence_boost=confidence_boost,
            reasons_skip=skip_reasons,
            llm_recommendation=llm_rec,
            llm_fair_probability=llm_fair,
            llm_reasoning=llm_reason,
        )

    # ------------------------------------------------------------------
    # Heuristiques
    # ------------------------------------------------------------------

    def _check_volume(
        self,
        market: dict,
        reasons: list[str],
        trade_amount: float = 0.0,
    ) -> None:
        """
        Liquidité dynamique: volume24h >= max(trade_amount * ratio, floor).

        Exemples avec ratio=10 et floor=200:
          trade=$10   → min_vol = max(100, 200) = 200 USDC
          trade=$50   → min_vol = max(500, 200) = 500 USDC
          trade=$200  → min_vol = max(2000, 200) = 2000 USDC
        """
        vol = float(market.get("volume24hr", 0) or 0)
        min_vol = max(
            trade_amount * self.liquidity_ratio if trade_amount > 0 else 0.0,
            self.min_volume_floor,
        )
        if vol < min_vol:
            reasons.append(f"low_volume:{vol:.0f}<{min_vol:.0f}(={trade_amount:.0f}x{self.liquidity_ratio:.0f})")

    def _check_spread(self, market: dict, reasons: list[str]) -> None:
        bid = float(market.get("bestBid", 0) or 0)
        ask = float(market.get("bestAsk", 1) or 1)
        if bid <= 0 or ask <= 0 or ask <= bid:
            return
        spread = (ask - bid) / ask
        if spread > self.max_spread_pct:
            reasons.append(f"spread:{spread:.1%}>{self.max_spread_pct:.0%}")

    def _check_end_date(self, market: dict, reasons: list[str]) -> None:
        end_date_str = market.get("endDate") or market.get("end_date_iso")
        if not end_date_str:
            return
        try:
            end_dt = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
            days_left = (end_dt - datetime.now(timezone.utc)).days
            if days_left > self.max_days_to_close:
                reasons.append(f"too_far:{days_left}d>{self.max_days_to_close}d")
        except (ValueError, AttributeError):
            pass

    def _check_price(self, yes_price: float, reasons: list[str]) -> None:
        if yes_price < self.min_price:
            reasons.append(f"price_too_low:{yes_price:.2f}<{self.min_price:.2f}")
        elif yes_price > self.max_price:
            reasons.append(f"price_too_high:{yes_price:.2f}>{self.max_price:.2f}")
