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
    Exécute les trades sur Polymarket via le CLOB.

    DRY_RUN=True  → simulation uniquement (log + DB)
    DRY_RUN=False → ordres signés et envoyés sur Polygon
    """

    def __init__(self):
        self.risk = RiskManager()
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

    # ------------------------------------------------------------------
    # Ouvrir une position (copy trade)
    # ------------------------------------------------------------------
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
        Retourne un CopiedTrade avec le statut final.
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

        # ── LIVE MODE ──
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

    # ------------------------------------------------------------------
    # Fermer une position (SELL) — appelé par ExitManager
    # ------------------------------------------------------------------
    async def close_position(
        self,
        token_id: str,
        entry_price: float,
        amount_usdc: float,
        market_question: str = "",
    ) -> bool:
        """
        Envoie un ordre SELL au marché pour fermer une position.

        En DRY RUN : simulé, retourne True.
        En LIVE    : ordre signé envoyé au CLOB Polymarket sur Polygon.

        Args:
            token_id:       Token Polymarket à vendre
            entry_price:    Prix d'entrée (utilisé pour calculer les shares)
            amount_usdc:    Montant USDC investi à l'achat
            market_question: Label du marché pour les logs

        Returns:
            True si l'ordre a été envoyé (ou simulé) avec succès.
        """
        # Nombre de shares achetées à l'entrée
        shares_to_sell = round(amount_usdc / entry_price, 4) if entry_price > 0 else 0
        label = market_question[:40] or token_id[:20]

        if settings.dry_run:
            logger.info(
                f"🟡 [DRY RUN] Would SELL {shares_to_sell} shares "
                f"(~${amount_usdc:.2f}) on {label}..."
            )
            return True

        # ── LIVE SELL ──
        try:
            client = self._get_client()
            order_args = MarketOrderArgs(
                token_id=token_id,
                amount=shares_to_sell,
                side=SELL,
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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _save_trade(self, trade: CopiedTrade) -> None:
        try:
            with get_db() as db:
                db.add(trade)
        except Exception as e:
            logger.error(f"Failed to save trade to DB: {e}")
