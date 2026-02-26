import asyncio
from datetime import datetime
from functools import partial
from typing import Optional

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import MarketOrderArgs
from py_clob_client.order_builder.constants import BUY, SELL

from bot.config import get_settings
from bot.database import get_db, CopiedTrade, TradeStatus
from bot.trading.risk import RiskManager
from bot.utils.logger import logger

settings = get_settings()


class TradingEngine:
    """
    Execute les trades sur Polymarket via le CLOB.
    DRY_RUN=True  -> simulation uniquement (log + DB)
    DRY_RUN=False -> ordres signes et envoyes sur Polygon

    FIX P0:      RiskManager injecte depuis main.py (instance partagee).
    FIX ENGINE-1: copy_trade() retourne None en cas d'exception CLOB
                  -> main.py ne fait plus register_position() sur FAILED.
    FIX ENGINE-2: close_position() guard entry_price <= 0 avant division.
    FIX ENGINE-3: tx_hash manquant -> 'MISSING_TX' + warning.
    FIX ENGINE-4: create_market_order() + post_order() sont synchrones
                  (py-clob-client). Executes dans run_in_executor pour
                  ne pas bloquer l'event loop asyncio pendant la requete HTTP.
    """

    def __init__(self, risk_manager: RiskManager):
        self.risk = risk_manager
        self._client: Optional[ClobClient] = None

    def _get_client(self) -> ClobClient:
        if self._client is None:
            try:
                self._client = ClobClient(
                    host=settings.polymarket_host,
                    key=settings.private_key,
                    chain_id=settings.chain_id,
                    signature_type=2,
                    funder=settings.proxy_wallet,
                )
            except Exception as e:
                logger.error(f"[ENGINE] ClobClient init failed: {e}")
                raise
        return self._client

    async def _clob_submit(
        self, order_args: MarketOrderArgs
    ) -> dict:
        """
        FIX ENGINE-4: wrappe les deux appels synchrones CLOB dans run_in_executor
        pour eviter de bloquer l'event loop asyncio.
        create_market_order() signe l'ordre (CPU-bound + crypto),
        post_order() envoie la requete HTTP (I/O-bound bloquant).
        Les deux sont delegues au thread pool par defaut.
        """
        loop = asyncio.get_event_loop()
        client = self._get_client()

        # Etape 1: signature (synchrone, CPU)
        signed_order = await loop.run_in_executor(
            None, partial(client.create_market_order, order_args)
        )
        # Etape 2: envoi HTTP (synchrone, I/O bloquant)
        response = await loop.run_in_executor(
            None, partial(client.post_order, signed_order)
        )
        return response

    async def copy_trade(
        self,
        source_wallet: str,
        token_id: str,
        side: str,
        price: float,
        source_amount: float,
        market_question: str = "",
        market_id: str = "",
    ) -> Optional[CopiedTrade]:
        trade_record = CopiedTrade(
            source_wallet_address=source_wallet, market_id=market_id,
            market_question=market_question, token_id=token_id,
            side=side, amount_usdc=source_amount, price=price,
        )

        if settings.dry_run:
            trade_record.status = TradeStatus.EXECUTED
            trade_record.skip_reason = "DRY_RUN"
            trade_record.executed_at = datetime.utcnow()
            logger.info(
                f"[DRY RUN] Would {side} ${source_amount} USDC "
                f"on {market_question[:50] or token_id[:20]}... @ {price:.3f}"
            )
            self._save_trade(trade_record)
            return trade_record

        try:
            side_const = BUY if side.upper() == "BUY" else SELL
            order_args = MarketOrderArgs(
                token_id=token_id, amount=source_amount, side=side_const,
            )
            # FIX ENGINE-4: appel non-bloquant via run_in_executor
            response = await self._clob_submit(order_args)

            # FIX ENGINE-3: tx_hash manquant -> warning explicite
            tx_hash = response.get("orderID") or "MISSING_TX"
            if tx_hash == "MISSING_TX":
                logger.warning(
                    f"[ENGINE] Missing orderID in CLOB response "
                    f"token={token_id[:20]} side={side_const}"
                )

            trade_record.status = TradeStatus.EXECUTED
            trade_record.tx_hash = tx_hash
            trade_record.executed_at = datetime.utcnow()
            logger.success(
                f"Trade EXECUTED: {side} ${source_amount} USDC "
                f"on {market_question[:40] or token_id[:20]}... | TX: {(tx_hash or '')[:12]}..."
            )
        except Exception as e:
            trade_record.status = TradeStatus.FAILED
            trade_record.skip_reason = str(e)[:200]
            logger.error(f"Trade FAILED: {e} | token={token_id[:20]}...")
            self._save_trade(trade_record)
            # FIX ENGINE-1: retour None -> main.py ne fait pas register_position()
            return None

        self._save_trade(trade_record)
        return trade_record

    async def close_position(
        self,
        token_id: str,
        entry_price: float,
        amount_usdc: float,
        market_question: str = "",
    ) -> bool:
        # FIX ENGINE-2: guard entry_price <= 0 avant division
        if entry_price <= 0:
            logger.error(
                f"[ENGINE] close_position aborted: invalid entry_price={entry_price} "
                f"token={token_id[:20]}..."
            )
            return False

        shares_to_sell = round(amount_usdc / entry_price, 4)
        if shares_to_sell <= 0:
            logger.error(
                f"[ENGINE] close_position aborted: computed 0 shares "
                f"(amount_usdc={amount_usdc} / entry_price={entry_price})"
            )
            return False

        label = market_question[:40] or token_id[:20]

        if settings.dry_run:
            logger.info(
                f"[DRY RUN] Would SELL {shares_to_sell} shares "
                f"(~${amount_usdc:.2f}) on {label}..."
            )
            return True

        try:
            order_args = MarketOrderArgs(
                token_id=token_id, amount=shares_to_sell, side=SELL,
            )
            # FIX ENGINE-4: appel non-bloquant via run_in_executor
            response = await self._clob_submit(order_args)
            tx_hash = response.get("orderID") or "MISSING_TX"
            logger.success(
                f"Position CLOSED: SELL {shares_to_sell} shares "
                f"on {label}... | TX: {(tx_hash or '')[:12]}..."
            )
            return True
        except Exception as e:
            logger.error(f"close_position FAILED: {e} | token={token_id[:20]}...")
            return False

    def _save_trade(self, trade: CopiedTrade) -> None:
        try:
            with get_db() as db:
                db.add(trade)
        except Exception as e:
            logger.error(f"Failed to save trade to DB: {e}")
