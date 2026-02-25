from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Polymarket
    polymarket_host: str = "https://clob.polymarket.com"
    polymarket_gamma_host: str = "https://gamma-api.polymarket.com"
    polymarket_data_host: str = "https://data-api.polymarket.com"
    private_key: str
    proxy_wallet: str
    chain_id: int = 137

    # Telegram
    telegram_bot_token: str
    telegram_chat_id: str

    # Database
    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    # Bot Settings
    scan_interval: int = Field(default=3, ge=1, le=60)
    max_trade_amount: float = Field(default=50.0, ge=1.0)
    min_win_rate: float = Field(default=0.70, ge=0.0, le=1.0)
    min_trades_count: int = Field(default=15, ge=1)
    whale_threshold: float = Field(default=500.0, ge=50.0)
    dry_run: bool = True

    # Risk Management
    max_position_pct: float = Field(default=0.10, ge=0.01, le=0.50)
    max_price: float = Field(default=0.90, ge=0.50, le=0.99)
    min_price: float = Field(default=0.05, ge=0.01, le=0.50)


@lru_cache()
def get_settings() -> Settings:
    return Settings()
