"""
Market Analyzer — PolyInsider Bot
===================================
Analyse un marché AVANT d'exécuter un trade copié.
Combine heuristiques rapides (sans LLM) + analyse LLM optionnelle (GPT-4o-mini).

Heuristiques (toujours actives, gratuites):
  - Liquidité: volume24h suffisant pour entrer/sortir
  - Spread: écart bid/ask pas trop large (slippage)
  - Clou du marché: end_date pas trop loin (capital immobilisé)
  - Prix: ni trop proche de 0 ni de 1 (peu de valeur espérée)

LLM (optionnel, nécessite LLM_ENABLED=true + OPENAI_API_KEY):
  - Demande à GPT-4o-mini si le marché est mispricé
  - Retourne un score de confiance supplémentaire

Usage:
  analyzer = MarketAnalyzer()
  result = await analyzer.analyze(market_data, yes_price=0.42)
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
    should_trade: bool          # True = OK pour copier
    confidence_boost: float     # bonus de confiance LLM (0.0 si pas de LLM)
    reasons_skip: list[str] = field(default_factory=list)   # raisons de skip
    llm_recommendation: str = "HOLD"    # BUY_YES | BUY_NO | HOLD
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
        min_volume_24h:     volume 24h minimum en USDC (défaut: 500)
        max_spread_pct:     spread bid/ask max en % (défaut: 10%)
        max_days_to_close:  nombre max de jours avant clôture du marché (défaut: 30)
        min_price:          prix YES minimum acceptable (défaut: 0.05)
        max_price:          prix YES maximum acceptable (défaut: 0.90)
        llm_agent:          LLMAgent injecté (créé automatiquement sinon)
    """

    def __init__(
        self,
        min_volume_24h: float = 500.0,
        max_spread_pct: float = 0.10,
        max_days_to_close: int = 30,
        min_price: float = 0.05,
        max_price: float = 0.90,
        llm_agent: LLMAgent | None = None,
    ) -> None:
        self.min_volume_24h    = min_volume_24h
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
    ) -> MarketAnalysis:
        """
        Analyse complète d'un marché.

        Args:
            market:    dict marché Polymarket (Gamma API format)
            yes_price: prix actuel du token YES (0.0-1.0)

        Returns:
            MarketAnalysis avec should_trade + détails
        """
        condition_id = market.get("conditionId", "")
        question = market.get("question", "")
        skip_reasons: list[str] = []

        # —— Heuristiques rapides (sans LLM) ———————————————————————
        self._check_volume(market, skip_reasons)
        self._check_spread(market, skip_reasons)
        self._check_end_date(market, skip_reasons)
        self._check_price(yes_price, skip_reasons)

        # Si déjà bloqué par les heuristiques, pas la peine d'appeler le LLM
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
                    # Boost de confiance: proportionnel au mispricing détecté
                    confidence_boost = min(signal.mispricing_pct * 2.0, 0.20)

                    # Si le LLM dit BUY_NO alors qu'on veut copier un BUY_YES → skip
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

    def _check_volume(self, market: dict, reasons: list[str]) -> None:
        """Rejette si le volume 24h est trop faible (marché illiquide)."""
        vol = float(market.get("volume24hr", 0) or 0)
        if vol < self.min_volume_24h:
            reasons.append(f"low_volume:{vol:.0f}<{self.min_volume_24h:.0f}")

    def _check_spread(self, market: dict, reasons: list[str]) -> None:
        """Rejette si le spread bid/ask est trop large (slippage élevé)."""
        bid = float(market.get("bestBid", 0) or 0)
        ask = float(market.get("bestAsk", 1) or 1)
        if bid <= 0 or ask <= 0 or ask <= bid:
            return  # pas de données bid/ask, on laisse passer
        spread = (ask - bid) / ask
        if spread > self.max_spread_pct:
            reasons.append(f"spread:{spread:.1%}>{self.max_spread_pct:.0%}")

    def _check_end_date(self, market: dict, reasons: list[str]) -> None:
        """Rejette si le marché se clôt dans trop longtemps (capital immobilisé)."""
        end_date_str = market.get("endDate") or market.get("end_date_iso")
        if not end_date_str:
            return  # pas de date connue, on laisse passer
        try:
            end_dt = datetime.fromisoformat(
                end_date_str.replace("Z", "+00:00")
            )
            now = datetime.now(timezone.utc)
            days_left = (end_dt - now).days
            if days_left > self.max_days_to_close:
                reasons.append(f"too_far:{days_left}d>{self.max_days_to_close}d")
        except (ValueError, AttributeError):
            pass  # format de date inconnu, on ignore

    def _check_price(self, yes_price: float, reasons: list[str]) -> None:
        """Rejette si le prix est trop extrême (faible valeur espérée)."""
        if yes_price < self.min_price:
            reasons.append(f"price_too_low:{yes_price:.2f}<{self.min_price:.2f}")
        elif yes_price > self.max_price:
            reasons.append(f"price_too_high:{yes_price:.2f}>{self.max_price:.2f}")
