from datetime import datetime
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
    Exécute les trades sur Polymarket via le CLOB.
    DRY_RUN=True  → simulation uniquement (log + DB)
    DRY_RUN=False → ordres signés et envoyés sur Polygon

    FIX P0: le RiskManager est désormais injecté depuis main.py (instance partagée).
    L'ancienne version créait son propre RiskManager interne isolé → les limites
    daily loss, drawdown et max_positions n'étaient jamais appliquées en LIVE.
    """

    def __init__(self, risk_manager: RiskManager):
        # FIX P0: plus de self.risk = RiskManager() isolé — on reçoit l'instance globale
        self.risk = risk_manager
        self._client: Optional[ClobClient] = None

    def _get_client(self) -> ClobClient:
        if self._client is None:
            self._client = ClobClient(
                host=settings.polymarket_host,
                key=settings.private_key,
                chain_id=settings.chain_id,
                signature_type=2,
                funder=settings.proxy_wallet,
            )
        return self._client

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
        # NOTE: main.py appelle déjà risk_manager.evaluate() avant copy_trade().
        # On n'appelle PAS self.risk.evaluate() ici pour éviter la double évaluation
        # sur la même instance. Le trade est supposé approuvé à ce stade.
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
                f"🟡 [DRY RUN] Would {side} ${source_amount} USDC "
                f"on {market_question[:50] or token_id[:20]}... @ {price:.3f}"
            )
            self._save_trade(trade_record)
            return trade_record

        try:
            client = self._get_client()
            side_const = BUY if side.upper() == "BUY" else SELL
            order_args = MarketOrderArgs(
                token_id=token_id, amount=source_amount, side=side_const,
            )
            signed_order = client.create_market_order(order_args)
            response = client.post_order(signed_order)
            tx_hash = response.get("orderID", "")
            trade_record.status = TradeStatus.EXECUTED
            trade_record.tx_hash = tx_hash
            trade_record.executed_at = datetime.utcnow()
            # register_position est appelé dans main.py après copy_trade()
            logger.success(
                f"✅ Trade EXECUTED: {side} ${source_amount} USDC "
                f"on {market_question[:40] or token_id[:20]}... | TX: {tx_hash[:12]}..."
            )
        except Exception as e:
            trade_record.status = TradeStatus.FAILED
            trade_record.skip_reason = str(e)[:200]
            logger.error(f"Trade FAILED: {e} | token={token_id[:20]}...")

        self._save_trade(trade_record)
        return trade_record

    async def close_position(
        self,
        token_id: str,
        entry_price: float,
        amount_usdc: float,
        market_question: str = "",
    ) -> bool:
        shares_to_sell = round(amount_usdc / entry_price, 4) if entry_price > 0 else 0
        label = market_question[:40] or token_id[:20]

        if settings.dry_run:
            logger.info(
                f"🟡 [DRY RUN] Would SELL {shares_to_sell} shares "
                f"(~${amount_usdc:.2f}) on {label}..."
            )
            return True

        try:
            client = self._get_client()
            order_args = MarketOrderArgs(
                token_id=token_id, amount=shares_to_sell, side=SELL,
            )
            signed_order = client.create_market_order(order_args)
            response = client.post_order(signed_order)
            tx_hash = response.get("orderID", "")
            logger.success(
                f"✅ Position CLOSED: SELL {shares_to_sell} shares "
                f"on {label}... | TX: {tx_hash[:12]}..."
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
