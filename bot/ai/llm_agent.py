"""
LLM Agent — inspiré de eiri0k/PolyMarket-AI-agent-trading

Agent autonome basé sur GPT-4o-mini qui analyse le contexte d'un marché
via RAG (Retrieval-Augmented Generation) sur des sources d'actualité récentes.
Retourne un score de confiance + une recommandation BUY_YES / BUY_NO / HOLD.

Activation: LLM_ENABLED=true + OPENAI_API_KEY dans .env

FIX LLM-1: _get_session() (anciennement _session_()) — nom propre sans tiret bas final
FIX LLM-2: aiohttp.ClientError ajouté au scope de retry (couvrait seulement requests avant)
FIX LLM-3: session fermée dans finally de batch_analyze (évite leak si exception)
"""
import asyncio
import json
from dataclasses import dataclass
from typing import Optional

import aiohttp

from bot.config import get_settings
from bot.utils.logger import logger

settings = get_settings()

SYSTEM_PROMPT = """You are an expert prediction market analyst specializing in Polymarket.
Your task: assess whether a prediction market is MISPRICED based on:
1. The current market probability (yes_price)
2. Recent news context provided
3. Your knowledge of the underlying event

Respond ONLY in valid JSON with this exact schema:
{
  "recommendation": "BUY_YES" | "BUY_NO" | "HOLD",
  "confidence": <float 0.0-1.0>,
  "fair_probability": <float 0.0-1.0>,
  "reasoning": "<one concise sentence>"
}

Only recommend BUY_YES or BUY_NO when:
- confidence > 0.70
- |fair_probability - yes_price| > 0.05 (at least 5% mispricing)
Otherwise always return HOLD."""


@dataclass
class LLMSignal:
    condition_id: str
    question: str
    current_price: float
    recommendation: str       # "BUY_YES" | "BUY_NO" | "HOLD"
    confidence: float         # 0.0 - 1.0
    fair_probability: float
    reasoning: str
    mispricing_pct: float     # abs(fair_probability - current_price)


class LLMAgent:
    """
    Agent LLM pour l'analyse de marchés Polymarket.
    Utilise GPT-4o-mini (rapport qualité/coût optimal) + NewsAPI pour le contexte.
    Désactivé par défaut — activer avec LLM_ENABLED=true + OPENAI_API_KEY.
    """

    OPENAI_URL = "https://api.openai.com/v1/chat/completions"
    NEWS_API_URL = "https://newsapi.org/v2/everything"
    MODEL = "gpt-4o-mini"

    def __init__(self) -> None:
        self.openai_key: str = getattr(settings, "openai_api_key", "") or ""
        self.news_key: str = getattr(settings, "news_api_key", "") or ""
        self.min_confidence: float = getattr(settings, "llm_min_confidence", 0.75)
        self._session: Optional[aiohttp.ClientSession] = None

    def is_enabled(self) -> bool:
        return bool(self.openai_key) and getattr(settings, "llm_enabled", False)

    def _get_session(self) -> aiohttp.ClientSession:
        """FIX LLM-1: nom propre (anciennement _session_() avec tiret bas final)."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=20)
            )
        return self._session

    # ------------------------------------------------------------------
    # RAG: récupère les news récentes pour enrichir le prompt
    # ------------------------------------------------------------------
    async def _fetch_news_context(self, query: str) -> str:
        if not self.news_key:
            return "No news context available."
        try:
            # FIX LLM-2: utilise _get_session() (nom corrigé)
            async with self._get_session().get(
                self.NEWS_API_URL,
                params={
                    "q": query[:100],
                    "sortBy": "publishedAt",
                    "pageSize": 3,
                    "language": "en",
                    "apiKey": self.news_key,
                },
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    articles = data.get("articles", [])
                    lines = [
                        f"- {a.get('title', '')} [{a.get('publishedAt', '')[:10]}]"
                        for a in articles[:3]
                    ]
                    return "\n".join(lines) if lines else "No recent news found."
        except aiohttp.ClientError as e:
            logger.debug(f"[LLM] News fetch error (aiohttp): {e}")
        except Exception as e:
            logger.debug(f"[LLM] News fetch error: {e}")
        return "News unavailable."

    # ------------------------------------------------------------------
    # Analyse un marché individuel
    # ------------------------------------------------------------------
    async def analyze_market(
        self,
        condition_id: str,
        question: str,
        yes_price: float,
    ) -> Optional[LLMSignal]:
        """Analyse un marché et retourne un signal si opportunité détectée."""
        if not self.is_enabled():
            return None

        news = await self._fetch_news_context(question)

        user_msg = (
            f"Market question: {question}\n"
            f"Current YES price (probability): {yes_price:.1%}\n"
            f"Recent news:\n{news}\n\n"
            "Is this market mispriced? Respond with JSON only."
        )

        try:
            # FIX LLM-2: utilise _get_session() (nom corrigé)
            async with self._get_session().post(
                self.OPENAI_URL,
                headers={
                    "Authorization": f"Bearer {self.openai_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 200,
                    "response_format": {"type": "json_object"},
                },
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"[LLM] OpenAI API error {resp.status}")
                    return None

                data = await resp.json()
                raw = data["choices"][0]["message"]["content"]
                parsed = json.loads(raw)

                rec = parsed.get("recommendation", "HOLD")
                conf = float(parsed.get("confidence", 0.0))
                fair = float(parsed.get("fair_probability", yes_price))
                reason = parsed.get("reasoning", "")
                misprice = abs(fair - yes_price)

                if conf < self.min_confidence or rec == "HOLD":
                    return None

                signal = LLMSignal(
                    condition_id=condition_id,
                    question=question,
                    current_price=yes_price,
                    recommendation=rec,
                    confidence=conf,
                    fair_probability=fair,
                    reasoning=reason,
                    mispricing_pct=misprice,
                )
                logger.info(
                    f"[LLM] {rec} on '{question[:50]}' "
                    f"| conf={conf:.0%} | misprice={misprice:.1%} "
                    f"| {reason}"
                )
                return signal

        except aiohttp.ClientError as e:
            logger.error(f"[LLM] Network error: {e}")
            return None
        except Exception as e:
            logger.error(f"[LLM] Analysis error: {e}")
            return None

    # ------------------------------------------------------------------
    # Analyse batch des N marchés les plus actifs
    # ------------------------------------------------------------------
    async def batch_analyze(
        self,
        markets: list[dict],
        top_n: int = 5,
    ) -> list[LLMSignal]:
        """Analyse les top_n marchés par volume et retourne les signaux détectés."""
        if not self.is_enabled():
            return []

        # Trie par volume 24h décroissant
        sorted_markets = sorted(
            markets,
            key=lambda m: float(m.get("volume24hr", 0)),
            reverse=True,
        )[:top_n]

        tasks = []
        for market in sorted_markets:
            tokens = market.get("tokens", [])
            yes_price = next(
                (
                    float(t.get("price", 0))
                    for t in tokens
                    if t.get("outcome", "").upper() == "YES"
                ),
                0.5,
            )
            tasks.append(
                self.analyze_market(
                    condition_id=market.get("conditionId", ""),
                    question=market.get("question", ""),
                    yes_price=yes_price,
                )
            )

        # FIX LLM-3: session fermée dans finally si exception pendant batch
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return [r for r in results if isinstance(r, LLMSignal)]
        except Exception as e:
            logger.error(f"[LLM] Batch analyze error: {e}")
            return []

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
