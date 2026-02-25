from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Polymarket ──────────────────────────────────────────────────────
    polymarket_host: str = "https://clob.polymarket.com"
    polymarket_gamma_host: str = "https://gamma-api.polymarket.com"
    polymarket_data_host: str = "https://data-api.polymarket.com"
    private_key: str
    proxy_wallet: str
    chain_id: int = 137

    # ── Telegram ────────────────────────────────────────────────────────
    telegram_bot_token: str
    telegram_chat_id: str

    # ── Database ────────────────────────────────────────────────────────
    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    # ── Bot Core ────────────────────────────────────────────────────────
    scan_interval: int = Field(default=3, ge=1, le=60)
    max_trade_amount: float = Field(default=50.0, ge=1.0)
    min_win_rate: float = Field(default=0.70, ge=0.0, le=1.0)
    min_trades_count: int = Field(default=15, ge=1)
    whale_threshold: float = Field(default=500.0, ge=50.0)
    dry_run: bool = True

    # ── Risk Management ─────────────────────────────────────────────────
    max_position_pct: float = Field(default=0.10, ge=0.01, le=0.50)
    max_price: float = Field(default=0.90, ge=0.50, le=0.99)
    min_price: float = Field(default=0.05, ge=0.01, le=0.50)

    # ── Conviction Filters (v2.0) ────────────────────────────────────────
    min_source_bet_usdc: float = Field(default=50.0, ge=1.0,
        description="Taille minimale du bet source pour être copié")
    min_wallet_score: float = Field(default=0.65, ge=0.0, le=1.0,
        description="Win rate minimum du wallet source")

    # ── Arbitrage Cross-Platform (v2.0) ──────────────────────────────────
    arb_enabled: bool = Field(default=True,
        description="Active le scanner Polymarket vs Kalshi")
    arb_min_profit_pct: float = Field(default=0.03, ge=0.01, le=0.20,
        description="Profit minimum pour signaler une opportunité d'arb")

    # ── Market Scanner (v2.0) ────────────────────────────────────────────
    market_scan_enabled: bool = Field(default=True,
        description="Active le scan haute échelle (10k+ marchés)")
    market_scan_max_markets: int = Field(default=5000, ge=100, le=20000,
        description="Nombre maximum de marchés à scanner")
    market_scan_every_n_loops: int = Field(default=100,
        description="Fréquence du market scan (toutes les N boucles)")

    # ── LLM Agent (v2.0) — optionnel ────────────────────────────────────
    llm_enabled: bool = Field(default=False,
        description="Active l'agent GPT-4o-mini (nécessite OPENAI_API_KEY)")
    openai_api_key: Optional[str] = Field(default=None,
        description="Clé API OpenAI")
    news_api_key: Optional[str] = Field(default=None,
        description="Clé NewsAPI pour enrichir le contexte LLM")
    llm_min_confidence: float = Field(default=0.75, ge=0.5, le=1.0,
        description="Confiance minimale pour agir sur un signal LLM")
    llm_scan_every_n_loops: int = Field(default=50,
        description="Fréquence de l'analyse LLM (toutes les N boucles)")
    llm_top_markets: int = Field(default=5, ge=1, le=20,
        description="Nombre de marchés analysés par cycle LLM")


@lru_cache()
def get_settings() -> Settings:
    return Settings()
