import asyncio
from datetime import datetime

from bot.config import get_settings
from bot.database import get_db, TrackedWallet, init_db
from bot.trading.polymarket import PolymarketDataClient
from bot.scanner.insider import InsiderScanner
from bot.scanner.whale import WhaleTracker
from bot.scanner.wallet_refresher import WalletRefresher
from bot.trading.engine import TradingEngine
from bot.notifications.telegram import TelegramNotifier
from bot.utils.logger import logger

settings = get_settings()


async def process_new_trade(
    trade: dict,
    wallet_address: str,
    engine: TradingEngine,
    notifier: TelegramNotifier,
    client: PolymarketDataClient,
) -> None:
    """Traite un nouveau trade détecté sur un wallet insider."""
    token_id = trade.get("asset", "")
    price = float(trade.get("price", 0))
    amount = float(trade.get("usdcSize", 0))
    side = trade.get("side", "BUY").upper()
    condition_id = trade.get("conditionId", "")

    if not token_id or price <= 0 or amount <= 0:
        return

    # Récupère les infos du marché
    market_info = await client.get_market_info(condition_id) if condition_id else None
    question = market_info.get("question", "") if market_info else ""

    copied_trade = await engine.copy_trade(
        source_wallet=wallet_address,
        token_id=token_id,
        side=side,
        price=price,
        source_amount=amount,
        market_question=question,
        market_id=condition_id,
    )

    if copied_trade:
        await notifier.notify_trade(copied_trade, market_question=question)


async def main_loop(
    scanner: InsiderScanner,
    whale_tracker: WhaleTracker,
    engine: TradingEngine,
    notifier: TelegramNotifier,
    client: PolymarketDataClient,
) -> None:
    """Boucle principale: scan toutes les wallets actives + whale tracker."""
    logger.info(f"Main loop started. Interval: {settings.scan_interval}s")

    while True:
        try:
            # 1. Scan les nouvelles baleines
            whale_events = await whale_tracker.scan()
            for event in whale_events:
                market_info = await client.get_market_info(event["condition_id"])
                question = market_info.get("question", "") if market_info else ""
                await notifier.notify_whale_event(
                    wallet=event["wallet"],
                    amount_usdc=event["amount_usdc"],
                    market_question=question,
                    side=event["side"],
                    price=event["price"],
                )

            # 2. Scan les nouveaux trades des wallets suivis
            with get_db() as db:
                active_wallets = (
                    db.query(TrackedWallet)
                    .filter(TrackedWallet.is_active == True)
                    .order_by(TrackedWallet.score.desc())
                    .all()
                )
                wallet_addresses = [w.address for w in active_wallets]

            if not wallet_addresses:
                logger.debug("No active wallets yet. Waiting for refresh...")
                await asyncio.sleep(settings.scan_interval)
                continue

            # Scan en parallèle pour tous les wallets actifs
            new_trades_tasks = [
                scanner.get_new_trades(addr) for addr in wallet_addresses
            ]
            all_new_trades = await asyncio.gather(*new_trades_tasks, return_exceptions=True)

            for wallet_addr, new_trades in zip(wallet_addresses, all_new_trades):
                if isinstance(new_trades, Exception):
                    logger.warning(f"Scan failed for {wallet_addr[:8]}...: {new_trades}")
                    continue

                for trade in new_trades:
                    await process_new_trade(
                        trade=trade,
                        wallet_address=wallet_addr,
                        engine=engine,
                        notifier=notifier,
                        client=client,
                    )

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Main loop error: {e}")

        await asyncio.sleep(settings.scan_interval)


async def run() -> None:
    """Point d'entrée principal du bot."""
    logger.info("=" * 50)
    logger.info(" PolyInsider Bot v1.0 starting...")
    logger.info(f" Mode: {'DRY RUN 🟡' if settings.dry_run else 'LIVE 🟢'}")
    logger.info("=" * 50)

    # Init DB
    init_db()

    # Instanciation des composants
    client = PolymarketDataClient()
    notifier = TelegramNotifier()
    scanner = InsiderScanner(client=client)
    whale_tracker = WhaleTracker(client=client)
    engine = TradingEngine()

    # Notification de démarrage
    await notifier.notify_startup(dry_run=settings.dry_run)

    # Lance le wallet refresher en background (toutes les 60min)
    refresher = WalletRefresher(
        scanner=scanner,
        notifier=notifier,
        interval_minutes=60,
    )
    await refresher.start()

    try:
        await main_loop(
            scanner=scanner,
            whale_tracker=whale_tracker,
            engine=engine,
            notifier=notifier,
            client=client,
        )
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    finally:
        await client.close()
        logger.info("Cleanup done. Bye!")


if __name__ == "__main__":
    asyncio.run(run())
