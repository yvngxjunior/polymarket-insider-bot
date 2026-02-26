"""Settings API endpoints for dashboard configuration."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from pathlib import Path
import os
from typing import Optional

router = APIRouter(prefix="/api/settings", tags=["settings"])


class BotSettings(BaseModel):
    """Bot configuration settings model."""
    
    # Core
    dry_run: bool = True
    scan_interval: int = Field(ge=1, le=60, default=3)
    initial_capital: float = Field(ge=1.0, default=500.0)
    
    # Risk Management
    max_positions: int = Field(ge=1, le=50, default=10)
    max_position_pct: float = Field(ge=0.01, le=0.50, default=0.10)
    max_price: float = Field(ge=0.50, le=0.99, default=0.90)
    min_price: float = Field(ge=0.01, le=0.50, default=0.05)
    daily_loss_limit_pct: float = Field(ge=0.01, le=1.0, default=0.15)
    drawdown_limit_pct: float = Field(ge=0.01, le=1.0, default=0.25)
    kelly_fraction: float = Field(ge=0.01, le=1.0, default=0.25)
    convergence_boost: float = Field(ge=1.0, le=3.0, default=1.5)
    
    # Filters
    min_win_rate: float = Field(ge=0.0, le=1.0, default=0.70)
    min_trades_count: int = Field(ge=1, default=15)
    min_source_bet_usdc: float = Field(ge=1.0, default=50.0)
    min_wallet_score: float = Field(ge=0.0, le=1.0, default=0.65)
    max_consecutive_losses: int = Field(ge=1, le=20, default=3)
    whale_threshold: float = Field(ge=50.0, default=500.0)
    
    # Features
    arb_enabled: bool = True
    arb_min_profit_pct: float = Field(ge=0.01, le=0.20, default=0.03)
    market_scan_enabled: bool = True
    market_scan_max_markets: int = Field(ge=100, le=20000, default=5000)
    llm_enabled: bool = False
    llm_min_confidence: float = Field(ge=0.5, le=1.0, default=0.75)
    
    # Advanced
    min_trade_usdc: float = Field(ge=0.5, default=2.0)
    kelly_fraction_sizer: float = Field(ge=0.01, le=1.0, default=0.25)
    log_level: str = Field(default="INFO")


def get_env_path() -> Path:
    """Get path to .env file (bot root)."""
    # Backend is in backend/, bot root is ../
    bot_root = Path(__file__).parent.parent.parent.parent
    env_path = bot_root / ".env"
    
    if not env_path.exists():
        raise FileNotFoundError(f".env not found at {env_path}")
    
    return env_path


def parse_env_value(value: str) -> bool | float | int | str:
    """Parse .env value to correct Python type."""
    value = value.strip()
    
    # Boolean
    if value.lower() in ["true", "false"]:
        return value.lower() == "true"
    
    # Try numeric
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def read_env_settings() -> BotSettings:
    """Read current settings from .env file."""
    env_path = get_env_path()
    
    # Parse .env
    env_vars = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip().lower()
                value = value.strip()
                env_vars[key] = parse_env_value(value)
    
    # Map to BotSettings
    try:
        return BotSettings(
            dry_run=env_vars.get("dry_run", True),
            scan_interval=env_vars.get("scan_interval", 3),
            initial_capital=env_vars.get("initial_capital", 500.0),
            max_positions=env_vars.get("max_positions", 10),
            max_position_pct=env_vars.get("max_position_pct", 0.10),
            max_price=env_vars.get("max_price", 0.90),
            min_price=env_vars.get("min_price", 0.05),
            daily_loss_limit_pct=env_vars.get("daily_loss_limit_pct", 0.15),
            drawdown_limit_pct=env_vars.get("drawdown_limit_pct", 0.25),
            kelly_fraction=env_vars.get("kelly_fraction", 0.25),
            convergence_boost=env_vars.get("convergence_boost", 1.5),
            min_win_rate=env_vars.get("min_win_rate", 0.70),
            min_trades_count=env_vars.get("min_trades_count", 15),
            min_source_bet_usdc=env_vars.get("min_source_bet_usdc", 50.0),
            min_wallet_score=env_vars.get("min_wallet_score", 0.65),
            max_consecutive_losses=env_vars.get("max_consecutive_losses", 3),
            whale_threshold=env_vars.get("whale_threshold", 500.0),
            arb_enabled=env_vars.get("arb_enabled", True),
            arb_min_profit_pct=env_vars.get("arb_min_profit_pct", 0.03),
            market_scan_enabled=env_vars.get("market_scan_enabled", True),
            market_scan_max_markets=env_vars.get("market_scan_max_markets", 5000),
            llm_enabled=env_vars.get("llm_enabled", False),
            llm_min_confidence=env_vars.get("llm_min_confidence", 0.75),
            min_trade_usdc=env_vars.get("min_trade_usdc", 2.0),
            kelly_fraction_sizer=env_vars.get("kelly_fraction_sizer", 0.25),
            log_level=env_vars.get("log_level", "INFO"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse settings: {e}")


def update_env_file(settings: BotSettings) -> None:
    """Update .env file with new settings, preserving comments and order."""
    env_path = get_env_path()
    
    # Read original file to preserve comments
    with open(env_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    # Map settings to env key names (uppercase with underscores)
    settings_map = {
        "DRY_RUN": str(settings.dry_run).lower(),
        "SCAN_INTERVAL": str(settings.scan_interval),
        "INITIAL_CAPITAL": str(settings.initial_capital),
        "MAX_POSITIONS": str(settings.max_positions),
        "MAX_POSITION_PCT": str(settings.max_position_pct),
        "MAX_PRICE": str(settings.max_price),
        "MIN_PRICE": str(settings.min_price),
        "DAILY_LOSS_LIMIT_PCT": str(settings.daily_loss_limit_pct),
        "DRAWDOWN_LIMIT_PCT": str(settings.drawdown_limit_pct),
        "KELLY_FRACTION": str(settings.kelly_fraction),
        "CONVERGENCE_BOOST": str(settings.convergence_boost),
        "MIN_WIN_RATE": str(settings.min_win_rate),
        "MIN_TRADES_COUNT": str(settings.min_trades_count),
        "MIN_SOURCE_BET_USDC": str(settings.min_source_bet_usdc),
        "MIN_WALLET_SCORE": str(settings.min_wallet_score),
        "MAX_CONSECUTIVE_LOSSES": str(settings.max_consecutive_losses),
        "WHALE_THRESHOLD": str(settings.whale_threshold),
        "ARB_ENABLED": str(settings.arb_enabled).lower(),
        "ARB_MIN_PROFIT_PCT": str(settings.arb_min_profit_pct),
        "MARKET_SCAN_ENABLED": str(settings.market_scan_enabled).lower(),
        "MARKET_SCAN_MAX_MARKETS": str(settings.market_scan_max_markets),
        "LLM_ENABLED": str(settings.llm_enabled).lower(),
        "LLM_MIN_CONFIDENCE": str(settings.llm_min_confidence),
        "MIN_TRADE_USDC": str(settings.min_trade_usdc),
        "KELLY_FRACTION_SIZER": str(settings.kelly_fraction_sizer),
        "LOG_LEVEL": settings.log_level,
    }
    
    # Update lines
    updated_lines = []
    for line in lines:
        stripped = line.strip()
        
        # Preserve comments and empty lines
        if not stripped or stripped.startswith("#"):
            updated_lines.append(line)
            continue
        
        # Update existing keys
        if "=" in line:
            key, _ = line.split("=", 1)
            key_upper = key.strip().upper()
            
            if key_upper in settings_map:
                updated_lines.append(f"{key.strip()}={settings_map[key_upper]}\n")
                # Mark as processed
                settings_map.pop(key_upper)
            else:
                # Preserve unchanged keys (PRIVATE_KEY, etc.)
                updated_lines.append(line)
        else:
            updated_lines.append(line)
    
    # Append any new keys that weren't in original file
    if settings_map:
        updated_lines.append("\n# Settings added by dashboard\n")
        for key, value in settings_map.items():
            updated_lines.append(f"{key}={value}\n")
    
    # Write back atomically (via temp file)
    temp_path = env_path.with_suffix(".env.tmp")
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.writelines(updated_lines)
        
        # Atomic replace
        temp_path.replace(env_path)
    except Exception as e:
        # Cleanup temp file on error
        if temp_path.exists():
            temp_path.unlink()
        raise HTTPException(status_code=500, detail=f"Failed to update .env: {e}")


@router.get("", response_model=BotSettings)
async def get_settings() -> BotSettings:
    """Get current bot settings from .env file."""
    try:
        return read_env_settings()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read settings: {e}")


@router.put("", response_model=BotSettings)
async def update_settings(settings: BotSettings) -> BotSettings:
    """Update bot settings in .env file.
    
    Note: Bot restart required for changes to take effect.
    """
    try:
        update_env_file(settings)
        return settings
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update settings: {e}")
