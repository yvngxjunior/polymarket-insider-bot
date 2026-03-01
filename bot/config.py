from functools import lru_cache
from typing import Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# Mots-clés de marchés à ignorer par défaut (sports, crypto daily, bruit).
# Surchargeables via WHALE_KEYWORDS_BLACKLIST dans .env (CSV, insensible à la casse).
DEFAULT_NOISE_KEYWORDS = [
    # Sports US
    "nba", "nfl", "nhl", "mlb", "nascar",
    "celtics", "nuggets", "lakers", "warriors", "bulls", "knicks",
    "nets", "heat", "suns", "bucks", "76ers", "raptors", "spurs",
    "mavericks", "rockets", "clippers", "timberwolves", "pistons",
    "pacers", "wizards", "magic", "hornets", "hawks", "cavaliers",
    "kings", "jazz", "thunder", "grizzlies", "pelicans", "trail blazers",
    "golden knights",
    "jets", "canucks", "rangers", "bruins", "maple leafs", "flyers",
    "penguins", "capitals", "lightning", "avalanche", "oilers", "flames",
    "predators", "blues", "stars", "wild", "coyotes", "sharks", "ducks",
    "red wings", "senators", "canadiens", "sabres", "blue jackets",
    # Sports internationaux
    "open:", "vs.", "spread:", "o/u", "moneyline",
    "tennis", "zverev", "nadal", "djokovic", "federer", "alcaraz",
    "mls", "premier league", "la liga", "bundesliga", "serie a",
    "ufc", "mma", "boxing",
    # Crypto daily / prix
    "bitcoin up or down",
    "eth up or down",
    "crypto up or down",
    # Joe Biden (marchés résolus connus)
    "joe biden",
    "will biden",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Polymarket ─────────────────────────────────────────────────────────────────
    polymarket_host: str = "https://clob.polymarket.com"
    polymarket_clob_host: str = Field(default="https://clob.polymarket.com", description="Alias for polymarket_host")
    polymarket_gamma_host: str = "https://gamma-api.polymarket.com"
    polymarket_data_host: str = "https://data-api.polymarket.com"
    private_key: str
    proxy_wallet: str
    chain_id: int = 137
    signature_type: int = Field(default=0, description="Signature type (0=EOA, 1=EIP712, 2=POLY_PROXY)")

    # ── Telegram ─────────────────────────────────────────────────────────────────
    telegram_bot_token: str
    telegram_chat_id: str

    # ── Database ────────────────────────────────────────────────────────────────
    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    # ── Logging ────────────────────────────────────────────────────────────────
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Niveau de log (DEBUG pour voir les réponses API brutes)",
    )

    # ── Bot Core ────────────────────────────────────────────────────────────────
    scan_interval: int = Field(default=3, ge=1, le=60)
    max_trade_amount: float = Field(default=50.0, ge=1.0)
    min_win_rate: float = Field(default=0.70, ge=0.0, le=1.0)
    min_trades_count: int = Field(default=15, ge=1)
    whale_threshold: float = Field(default=500.0, ge=50.0)
    dry_run: bool = True

    # ── Capital ──────────────────────────────────────────────────────────────────
    initial_capital: float = Field(
        default=500.0,
        ge=1.0,
        description="Capital de départ en USDC. Utilisé comme fallback si la DB est vide.",
    )

    # ── Risk Management ──────────────────────────────────────────────────────────
    max_position_pct: float = Field(default=0.10, ge=0.01, le=0.50)
    max_price: float = Field(default=0.90, ge=0.50, le=0.99)
    min_price: float = Field(default=0.05, ge=0.01, le=0.50)

    max_positions: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Nombre maximum de positions ouvertes simultanément.",
    )
    daily_loss_limit_pct: float = Field(
        default=0.15,
        ge=0.01,
        le=1.0,
        description="Perte journalière max en % du capital avant de bloquer les trades. Ex: 0.15 = 15%%.",
    )
    drawdown_limit_pct: float = Field(
        default=0.25,
        ge=0.01,
        le=1.0,
        description="Drawdown global max depuis le pic avant de bloquer les trades. Ex: 0.25 = 25%%.",
    )
    kelly_fraction: float = Field(
        default=0.25,
        ge=0.01,
        le=1.0,
        description="Fraction Kelly appliquée (Quarter-Kelly = 0.25 par défaut).",
    )
    convergence_boost: float = Field(
        default=1.5,
        ge=1.0,
        le=3.0,
        description="Multiplicateur de taille appliqué quand plusieurs insiders convergent.",
    )

    # ── Position Sizer ────────────────────────────────────────────────────────────
    min_trade_usdc: float = Field(
        default=2.0,
        ge=0.5,
        description="Montant minimum d'un trade en USDC (en dessous, le trade est ignoré).",
    )
    kelly_fraction_sizer: float = Field(
        default=0.25,
        ge=0.01,
        le=1.0,
        description="Fraction Kelly pour PositionSizer (peut différer de kelly_fraction si besoin).",
    )

    # ── Conviction Filters ────────────────────────────────────────────────────────
    min_source_bet_usdc: float = Field(default=50.0, ge=1.0,
        description="Taille minimale du bet source pour être copié")
    min_wallet_score: float = Field(default=0.65, ge=0.0, le=1.0,
        description="Win rate minimum du wallet source")
    max_consecutive_losses: int = Field(
        default=3,
        ge=1,
        le=20,
        description="Nombre de pertes consécutives au-delà duquel un wallet est ignoré.",
    )

    # ── Whale keyword filter ──────────────────────────────────────────────────────
    whale_keywords_blacklist: str = Field(
        default="",
        description=(
            "CSV de mots-clés à exclure des Whale Alerts (insensible à la casse). "
            "Si vide, utilise la liste de bruit par défaut (sports, crypto daily, etc.). "
            "Pour désactiver complètement le filtre: WHALE_KEYWORDS_BLACKLIST=__none__"
        ),
    )

    # ── Position Sizer Tiered (v2.7) ──────────────────────────────────────────────
    tiered_multipliers: str = Field(
        default="",
        description=(
            "Multiplicateurs dégressifs selon la taille du trade source (CSV). "
            "Format: \"min-max:mult,min+:mult\" (USD). "
            "Exemple: TIERED_MULTIPLIERS=1-50:1.0,50-500:0.3,500-5000:0.05,5000+:0.01. "
            "Laisser vide pour Kelly pur sans multiplicateur."
        ),
    )

    # ── Arbitrage Cross-Platform ──────────────────────────────────────────────────
    arb_enabled: bool = Field(default=True,
        description="Active le scanner Polymarket vs Kalshi")
    arb_min_profit_pct: float = Field(default=0.03, ge=0.01, le=0.20,
        description="Profit minimum pour signaler une opportunité d'arb")

    # ── Market Scanner ────────────────────────────────────────────────────────────
    market_scan_enabled: bool = Field(default=True,
        description="Active le scan haute échelle (10k+ marchés)")
    market_scan_max_markets: int = Field(default=5000, ge=100, le=20000,
        description="Nombre maximum de marchés à scanner")
    market_scan_every_n_loops: int = Field(default=100,
        description="Fréquence du market scan (toutes les N boucles)")

    # ── LLM Agent — optionnel ──────────────────────────────────────────────────────
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

    # ── Wallet Whitelist / Blacklist ───────────────────────────────────────────────
    wallet_whitelist: str = Field(
        default="",
        description="CSV d'adresses toujours suivies (bypass filtres de score). Ex: 0xAAA,0xBBB",
    )
    wallet_blacklist: str = Field(
        default="",
        description="CSV d'adresses jamais copiées. Ex: 0xCCC,0xDDD",
    )

    # ── Health Monitor ─────────────────────────────────────────────────────────────
    health_silence_threshold_min: int = Field(
        default=30,
        description="Minutes sans activité avant alerte Telegram",
    )
    health_check_interval_sec: int = Field(
        default=300,
        description="Fréquence de vérification de santé en secondes (défaut: 5min)",
    )
    health_alert_cooldown_min: int = Field(
        default=60,
        description="Minutes minimum entre deux alertes de santé (anti-spam)",
    )

    # ── Helpers ───────────────────────────────────────────────────────────────────

    def get_whitelist(self) -> set[str]:
        """Retourne la whitelist comme un set d'adresses en minuscules."""
        if not self.wallet_whitelist:
            return set()
        return {a.strip().lower() for a in self.wallet_whitelist.split(",") if a.strip()}

    def get_blacklist(self) -> set[str]:
        """Retourne la blacklist comme un set d'adresses en minuscules."""
        if not self.wallet_blacklist:
            return set()
        return {a.strip().lower() for a in self.wallet_blacklist.split(",") if a.strip()}

    def get_whale_keywords_blacklist(self) -> list[str]:
        """
        Retourne la liste de mots-clés à filtrer pour les Whale Alerts.
        - Si WHALE_KEYWORDS_BLACKLIST=__none__ dans .env : filtre désactivé
        - Si vide ou absent                              : DEFAULT_NOISE_KEYWORDS
        - Sinon                                          : mots-clés fournis
        """
        val = self.whale_keywords_blacklist.strip()
        if val == "__none__":
            return []
        if not val:
            return DEFAULT_NOISE_KEYWORDS
        return [k.strip().lower() for k in val.split(",") if k.strip()]


@lru_cache()
def get_settings() -> Settings:
    return Settings()
