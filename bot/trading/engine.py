import asyncio
from datetime import datetime
from typing import Optional

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import MarketOrderArgs
from py_clob_client.order_builder.constants import BUY, SELL

from bot.config import get_settings
from bot.database import get_db, CopiedTrade, TradeStatus
from bot.trading.risk import RiskManager, TradeDecision
from bot.utils.logger import logger

settings = get_settings()


class TradingEngine:
    """
    Exécute les trades copiés sur Polymarket via le CLOB.

    En mode DRY_RUN=True: les trades sont simulés et loggués uniquement.
    En mode DRY_RUN=False: les ordres sont signés et envoyés sur la chain.
    """

    def __init__(self):
        self.risk = RiskManager()
        self._client: Optional[ClobClient] = None

    def _get_client(self) -> ClobClient:
        """Initialise le client CLOB une seule fois (lazy)."""
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
        """
        Tente de copier un trade détecté.

        Returns:
            CopiedTrade avec le statut final (EXECUTED / SKIPPED / FAILED)
        """
        decision: TradeDecision = self.risk.evaluate(
            token_id=token_id,
            price=price,
            source_amount=source_amount,
        )

        trade_record = CopiedTrade(
            source_wallet_address=source_wallet,
            market_id=market_id,
            market_question=market_question,
            token_id=token_id,
            side=side,
            amount_usdc=decision.amount_usdc,
            price=price,
        )

        if not decision.approved:
            trade_record.status = TradeStatus.SKIPPED
            trade_record.skip_reason = decision.reason
            logger.warning(
                f"Trade SKIPPED — {decision.reason} "
                f"(wallet={source_wallet[:8]}..., token={token_id[:12]}...)"
            )
            self._save_trade(trade_record)
            return trade_record

        if settings.dry_run:
            trade_record.status = TradeStatus.EXECUTED
            trade_record.skip_reason = "DRY_RUN"
            trade_record.executed_at = datetime.utcnow()
            logger.info(
                f"🟡 [DRY RUN] Would {side} ${decision.amount_usdc} USDC "
                f"on {market_question[:50] or token_id[:20]}... "
                f"@ {price:.3f} (source: {source_wallet[:8]}...)"
            )
            self._save_trade(trade_record)
            return trade_record

        # -- LIVE MODE --
        try:
            client = self._get_client()
            side_const = BUY if side.upper() == "BUY" else SELL

            order_args = MarketOrderArgs(
                token_id=token_id,
                amount=decision.amount_usdc,
                side=side_const,
            )
            signed_order = client.create_market_order(order_args)
            response = client.post_order(signed_order)

            tx_hash = response.get("orderID", "")
            trade_record.status = TradeStatus.EXECUTED
            trade_record.tx_hash = tx_hash
            trade_record.executed_at = datetime.utcnow()

            self.risk.register_position(token_id)

            logger.success(
                f"✅ Trade EXECUTED: {side} ${decision.amount_usdc} USDC "
                f"on {market_question[:40] or token_id[:20]}... "
                f"| TX: {tx_hash[:12]}..."
            )

        except Exception as e:
            trade_record.status = TradeStatus.FAILED
            trade_record.skip_reason = str(e)[:200]
            logger.error(f"Trade FAILED: {e} | token={token_id[:20]}...")

        self._save_trade(trade_record)
        return trade_record

    def _save_trade(self, trade: CopiedTrade) -> None:
        """Persiste le trade en base de données."""
        try:
            with get_db() as db:
                db.add(trade)
        except Exception as e:
            logger.error(f"Failed to save trade to DB: {e}")
