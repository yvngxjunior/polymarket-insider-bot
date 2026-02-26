import asyncio
from datetime import datetime
from functools import partial
from typing import Optional

import aiohttp

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import MarketOrderArgs
from py_clob_client.order_builder.constants import BUY, SELL

from bot.config import get_settings
from bot.database import get_db, CopiedTrade, TradeStatus
from bot.trading.risk import RiskManager
from bot.utils.logger import logger

settings = get_settings()

# Polymarket minimum order size en USDC
_MIN_ORDER_USD = 1.0
# Nombre maximum de tranches pour fragmenter un gros ordre
_MAX_SLICES = 3


class TradingEngine:
    """
    Execute les trades sur Polymarket via le CLOB.
    DRY_RUN=True  -> simulation uniquement (log + DB)
    DRY_RUN=False -> ordres signes et envoyes sur Polygon

    FIX ENGINE-1: copy_trade() retourne None en cas d'exception CLOB
    FIX ENGINE-2: close_position() guard entry_price <= 0 avant division.
    FIX ENGINE-3: tx_hash manquant -> 'MISSING_TX' + warning.
    FIX ENGINE-4: appels synchrones CLOB dans run_in_executor.
    FIX ENGINE-5: lecture du order book réel avant chaque BUY + slicing.
    FIX ENGINE-6: slash manquant dans l'URL /book (404 silencieux).
    FIX ENGINE-7: close_position passait shares au lieu d'USDC au CLOB.
    FIX ENGINE-8: guard source_amount <= 0 avant tout ordre.
    FIX ENGINE-9: _http_session partagée (plus de new ClientSession() à chaque appel).
    """

    def __init__(self, risk_manager: RiskManager):
        self.risk = risk_manager
        self._client: Optional[ClobClient] = None
        # FIX ENGINE-9: session HTTP unique, créée lazy, réutilisée sur toute la durée de vie
        self._http_session: Optional[aiohttp.ClientSession] = None

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

    def _get_http_session(self) -> aiohttp.ClientSession:
        """FIX ENGINE-9: session HTTP partagée, créée une seule fois."""
        if self._http_session is None or self._http_session.closed:
            self._http_session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=5)
            )
        return self._http_session

    async def close(self) -> None:
        """Fermeture propre de la session HTTP au shutdown."""
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
            logger.debug("[ENGINE] HTTP session closed.")

    async def _clob_submit(
        self, order_args: MarketOrderArgs
    ) -> dict:
        """
        FIX ENGINE-4: wrappe les appels synchrones CLOB dans run_in_executor.
        """
        loop = asyncio.get_event_loop()
        client = self._get_client()
        signed_order = await loop.run_in_executor(
            None, partial(client.create_market_order, order_args)
        )
        response = await loop.run_in_executor(
            None, partial(client.post_order, signed_order)
        )
        return response

    # ------------------------------------------------------------------
    # FIX ENGINE-5 + ENGINE-6 + ENGINE-9: order book réel, session partagée
    # ------------------------------------------------------------------

    async def _fetch_best_ask(
        self, token_id: str
    ) -> Optional[tuple[float, float]]:
        """
        Récupère le meilleur ask disponible sur le CLOB pour token_id.
        Retourne (price, size_usd) ou None si indisponible.
        FIX ENGINE-9: utilise self._get_http_session() au lieu d'une new session.
        """
        url = f"{settings.polymarket_host}/book?token_id={token_id}"
        try:
            session = self._get_http_session()
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.debug(
                        f"[ENGINE] _fetch_best_ask HTTP {resp.status} "
                        f"for {token_id[:16]}..."
                    )
                    return None
                data = await resp.json()

            asks = data.get("asks") or []
            if not asks:
                return None

            best = min(asks, key=lambda x: float(x.get("price", 999)))
            price = float(best["price"])
            size_tokens = float(best["size"])
            size_usd = size_tokens * price
            return price, size_usd
        except Exception as e:
            logger.debug(f"[ENGINE] _fetch_best_ask error: {e}")
            return None

    async def _execute_buy_sliced(
        self,
        token_id: str,
        total_usd: float,
        trade_record: CopiedTrade,
    ) -> bool:
        """
        FIX ENGINE-5: exécute un BUY en lisant le order book.
        Découpe en tranches (max _MAX_SLICES) si le meilleur ask
        ne couvre pas le montant total demandé.
        Retourne True si au moins une tranche est exécutée avec succès.
        """
        remaining = total_usd
        slices_done = 0
        tx_hashes: list[str] = []

        for i in range(_MAX_SLICES):
            if remaining < _MIN_ORDER_USD:
                break

            best = await self._fetch_best_ask(token_id)
            if best is None:
                logger.warning(
                    f"[ENGINE] No asks available for {token_id[:16]}... "
                    f"(slice {i+1}/{_MAX_SLICES})"
                )
                break

            ask_price, ask_size_usd = best
            slice_usd = min(remaining, ask_size_usd)

            if slice_usd < _MIN_ORDER_USD:
                logger.debug(
                    f"[ENGINE] Best ask size ${ask_size_usd:.2f} < min ${_MIN_ORDER_USD} "
                    f"— stopping slices"
                )
                break

            logger.debug(
                f"[ENGINE] Slice {i+1}/{_MAX_SLICES}: "
                f"${slice_usd:.2f} @ {ask_price:.4f} "
                f"(remaining=${remaining:.2f})"
            )

            order_args = MarketOrderArgs(
                token_id=token_id,
                amount=slice_usd,
                side=BUY,
            )
            response = await self._clob_submit(order_args)

            if response.get("success") is True or response.get("orderID"):
                tx = response.get("orderID") or "MISSING_TX"
                tx_hashes.append(tx)
                remaining -= slice_usd
                slices_done += 1
                logger.debug(
                    f"[ENGINE] Slice {i+1} OK — TX:{tx[:12]}... "
                    f"remaining=${remaining:.2f}"
                )
            else:
                err = response.get("error") or response.get("errorMsg") or str(response)
                logger.warning(f"[ENGINE] Slice {i+1} FAILED: {err}")
                break

        if slices_done > 0:
            trade_record.tx_hash = ",".join(tx_hashes)
            trade_record.status = TradeStatus.EXECUTED
            trade_record.executed_at = datetime.utcnow()
            filled = total_usd - remaining
            logger.success(
                f"Trade EXECUTED ({slices_done} slice{'s' if slices_done > 1 else ''}): "
                f"BUY ${filled:.2f} USDC "
                f"on {trade_record.market_question[:40] or token_id[:20]}... "
                f"| TX: {(tx_hashes[0] or '')[:12]}..."
            )
            return True

        return False

    # ------------------------------------------------------------------
    # Interface publique
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
        # FIX ENGINE-8: guard montant invalide avant tout traitement
        if source_amount <= 0:
            logger.error(
                f"[ENGINE] copy_trade aborted: source_amount={source_amount} "
                f"token={token_id[:20]}..."
            )
            return None

        trade_record = CopiedTrade(
            source_wallet_address=source_wallet, market_id=market_id,
            market_question=market_question, token_id=token_id,
            side=side, amount_usdc=source_amount, price=price,
        )

        if settings.dry_run:
            best = await self._fetch_best_ask(token_id)
            ask_info = (
                f" | best ask: ${best[1]:.2f} @ {best[0]:.4f}"
                if best else " | best ask: N/A"
            )
            trade_record.status = TradeStatus.EXECUTED
            trade_record.skip_reason = "DRY_RUN"
            trade_record.executed_at = datetime.utcnow()
            logger.info(
                f"[DRY RUN] Would {side} ${source_amount:.2f} USDC "
                f"on {market_question[:50] or token_id[:20]}... "
                f"@ {price:.3f}{ask_info}"
            )
            self._save_trade(trade_record)
            return trade_record

        try:
            if side.upper() == "BUY":
                success = await self._execute_buy_sliced(
                    token_id=token_id,
                    total_usd=source_amount,
                    trade_record=trade_record,
                )
                if not success:
                    trade_record.status = TradeStatus.FAILED
                    trade_record.skip_reason = "No asks / all slices failed"
                    logger.error(
                        f"Trade FAILED: no fills on "
                        f"{market_question[:40] or token_id[:20]}..."
                    )
                    self._save_trade(trade_record)
                    return None
            else:
                order_args = MarketOrderArgs(
                    token_id=token_id, amount=source_amount, side=SELL,
                )
                response = await self._clob_submit(order_args)
                tx_hash = response.get("orderID") or "MISSING_TX"
                if tx_hash == "MISSING_TX":
                    logger.warning(
                        f"[ENGINE] Missing orderID — token={token_id[:20]} side=SELL"
                    )
                trade_record.status = TradeStatus.EXECUTED
                trade_record.tx_hash = tx_hash
                trade_record.executed_at = datetime.utcnow()
                logger.success(
                    f"Trade EXECUTED: SELL ${source_amount:.2f} USDC "
                    f"on {market_question[:40] or token_id[:20]}... "
                    f"| TX: {(tx_hash or '')[:12]}..."
                )
        except Exception as e:
            trade_record.status = TradeStatus.FAILED
            trade_record.skip_reason = str(e)[:200]
            logger.error(f"Trade FAILED: {e} | token={token_id[:20]}...")
            self._save_trade(trade_record)
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
        """
        Ferme une position en envoyant un ordre SELL au CLOB.
        FIX ENGINE-2: guard entry_price <= 0.
        FIX ENGINE-7: amount_usdc directement (pas de division par entry_price).
        """
        if entry_price <= 0:
            logger.error(
                f"[ENGINE] close_position aborted: invalid entry_price={entry_price} "
                f"token={token_id[:20]}..."
            )
            return False

        if amount_usdc <= 0:
            logger.error(
                f"[ENGINE] close_position aborted: amount_usdc={amount_usdc} "
                f"token={token_id[:20]}..."
            )
            return False

        label = market_question[:40] or token_id[:20]

        if settings.dry_run:
            logger.info(
                f"[DRY RUN] Would SELL ${amount_usdc:.2f} USDC on {label}..."
            )
            return True

        try:
            order_args = MarketOrderArgs(
                token_id=token_id,
                amount=amount_usdc,
                side=SELL,
            )
            response = await self._clob_submit(order_args)
            tx_hash = response.get("orderID") or "MISSING_TX"
            if tx_hash == "MISSING_TX":
                logger.warning(
                    f"[ENGINE] Missing orderID on close — token={token_id[:20]}"
                )
            logger.success(
                f"Position CLOSED: SELL ${amount_usdc:.2f} USDC "
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
