import asyncio
from decimal import Decimal, ROUND_DOWN
from functools import wraps
from typing import Callable, Any

import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from bot.utils.logger import logger


def retry_on_failure(max_attempts: int = 3, wait_min: float = 1.0, wait_max: float = 10.0):
    """
    Décorateur de retry avec backoff exponentiel.
    Usage: @retry_on_failure(max_attempts=3)
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=wait_min, max=wait_max),
        retry=retry_if_exception_type(
            (requests.RequestException, ConnectionError, TimeoutError)
        ),
        before_sleep=lambda retry_state: logger.warning(
            f"Retry {retry_state.attempt_number}/{max_attempts} — "
            f"{retry_state.outcome.exception()}"
        ),
    )


def safe_async(coro_func: Callable) -> Callable:
    """Wrapper pour capturer les exceptions dans les coroutines async sans planter le bot."""

    @wraps(coro_func)
    async def wrapper(*args, **kwargs) -> Any:
        try:
            return await coro_func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Unhandled error in {coro_func.__name__}: {e}")
            return None

    return wrapper


def round_usdc(amount: float, decimals: int = 2) -> float:
    """Arrondit un montant USDC vers le bas pour éviter les overflow."""
    return float(
        Decimal(str(amount)).quantize(
            Decimal(f'0.{"0" * decimals}'), rounding=ROUND_DOWN
        )
    )


def score_wallet(
    win_rate: float, total_trades: int, total_profit: float
) -> float:
    """
    Score composite d'un wallet sur 100.
    Pondération: 50% win_rate, 30% volume de trades, 20% profit.
    """
    wr_score = min(win_rate * 100, 100) * 0.50
    trade_score = min(total_trades / 100 * 100, 100) * 0.30
    profit_score = min(max(total_profit / 1000 * 100, 0), 100) * 0.20
    return round(wr_score + trade_score + profit_score, 2)


def get_score_label(score: float) -> str:
    """Convertit le score numérique en label A/B/C/D."""
    if score >= 75:
        return "🟢 A (Elite)"
    elif score >= 55:
        return "🔵 B (Good)"
    elif score >= 35:
        return "🟡 C (Average)"
    return "🔴 D (Weak)"


async def sleep_with_log(seconds: float, reason: str = "") -> None:
    """Sleep async avec log optionnel."""
    if reason:
        logger.debug(f"Sleeping {seconds}s — {reason}")
    await asyncio.sleep(seconds)
