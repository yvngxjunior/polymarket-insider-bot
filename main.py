"""
PolyInsider Bot v3.3
=====================
Architecture 7 phases + 5 background tasks:
  1. Whale scan         — baleines sur nouveaux marchés
  1.5 Whale Exit Monitor — track REDEEM/SELL from whales [NEW v3.3]
  2. Convergence scan   — plusieurs insiders sur même marché
  3. Insider copy       — copy trading wallets scorés
  4. Arbitrage scan     — Polymarket vs Kalshi             [périodique]
  5. Market scan        — 5 000+ marchés arb interne       [périodique]
  6. LLM analysis       — GPT-4o-mini + RAG actualités     [périodique, optionnel]
  7. Performance report — win rate / PnL / trades          [périodique]
  └ WalletRefresher    — refresh + discovery wallets      [background, 60min]
  └ ExitManager        — TP1(50%) / TP2 / SL / durée max  [background, 60s]
  └ HealthMonitor      — silence detection + alerte Telegram [background, 5min]
  └ FeaturesManager    — Trailing SL + Auto Discovery      [background]
  └ WhaleExitMonitor   — track whale exits + alerts       [background, 5min] [NEW v3.3]

v3.3 NEW FEATURES:
  ✨ WHALE EXIT TRACKING — Monitor when whales REDEEM/SELL positions
     - Passive: Analyze exit patterns for conviction scoring
     - Active: Alert when whale exits a market you hold
     - Optional: Auto-exit on whale SELL signal (risky, disabled by default)

v3.2 features:
  ✨ TRAILING STOP-LOSS — Dynamic SL that follows price (activates at +15%)
  ✨ AUTO WALLET DISCOVERY — Scrapes Polymarket leaderboard every 24h
  ✨ AUTO-REFRESH AFTER WHALE ADD — Immediate scanner refresh when whales auto-added

v2.8-3.2 fixes:
  - FIX MAIN-2/3   float(None) crash + refresher.stop() manquant
  - FIX CMD-1      settings mutation Pydantic v2
  - FIX INSIDER-4  get_new_trades() timeout par wallet
  - IMPROV-8       process_new_trade enveloppé dans try/except
  - FIX CONV-3     convergence boost x1.5 mort → is_convergence passé à evaluate()
  - FIX CONV-4     fenêtre détection basée sur now() au lieu de timestamp API
  - FIX RISK-6     INSERT portfolio_snapshot jamais committé
  - FIX RISK-7     total_capital hardcodé 500 → settings.initial_capital
  - FIX FILTER-1   rate-limit query status case-sensitive
  - FIX MAIN-4     performance_tracker.record_trade bare except → logger.warning
  - FIX MAIN-5     convergence.process_trade logger.debug → logger.warning
  - FIX MAIN-6     _open_positions accès privé → open_positions_count() public
  - FIX MAIN-7     aiohttp.ClientSession LLM recréé chaque cycle → session unique
  - FIX ENGINE-9   _http_session partagée dans TradingEngine
  - FIX DB-3       migrations _SAFE_MIGRATIONS sur PostgreSQL
  - FIX MAIN-8     engine.close() dans asyncio.gather shutdown
  - FIX MAIN-9     Auto-refresh scanner after whale auto-add
"""
import asyncio
import signal
import sys

import aiohttp

from bot.config import get_settings
from bot.database import get_db, TrackedWallet, init_db
from bot.trading.polymarket import PolymarketDataClient
from bot.scanner.insider import InsiderScanner, _safe_float
from bot.scanner.whale import WhaleTracker
from bot.scanner.whale_exit_monitor import WhaleExitMonitor  # NEW v3.3
from bot.scanner.wallet_refresher import WalletRefresher
from bot.scanner.wallet_scanner import WalletScanner
from bot.scanner.convergence import ConvergenceDetector
from bot.scanner.arbitrage import ArbitrageScanner
from bot.scanner.market_scanner import MarketScanner
from bot.trading.engine import TradingEngine
from bot.trading.risk import RiskManager
from bot.trading.position_manager import PositionManager
from bot.trading.sizing import PositionSizer
from bot.trading.filters import ConvictionFilter
from bot.trading.exit_manager import ExitManager
from bot.notifications.telegram import TelegramNotifier
from bot.notifications.commands import BotCommandHandler
from bot.notifications.health import HealthMonitor
from bot.analytics.performance import PerformanceTracker
from bot.ai.llm_agent import LLMAgent
from bot.utils.logger import logger
from bot.features_integration import get_features_manager

settings = get_settings()


# ────────────────────────────────────────────────────────────────────────────
async def process_new_trade(
    trade: dict,
    wallet_address: str,
    wallet_score: float,
    consecutive_losses: int,
    entry_timing_score: float,
    engine: TradingEngine,
    notifier: TelegramNotifier,
    client: PolymarketDataClient,
    risk_manager: RiskManager,
    position_manager: PositionManager,
    performance_tracker: PerformanceTracker,
    conv_filter: ConvictionFilter,
    sizer: PositionSizer,
    health_monitor: HealthMonitor,
    convergence_detector: ConvergenceDetector,
) -> None:
    token_id     = trade.get("asset", "")
    price        = _safe_float(trade.get("price"), 0.0)
    amount       = _safe_float(trade.get("usdcSize"), 0.0)
    side         = trade.get("side", "BUY").upper()
    condition_id = trade.get("conditionId", "")
    timestamp    = _safe_float(trade.get("timestamp"), 0.0)

    if not token_id or price <= 0 or amount <= 0:
        return

    blacklist = settings.get_blacklist()
    if wallet_address.lower() in blacklist:
        logger.debug(f"[BLACKLIST] Skipped {wallet_address[:10]}")
        return

    whitelist      = settings.get_whitelist()
    is_whitelisted = wallet_address.lower() in whitelist
    effective_score = 1.0 if is_whitelisted else wallet_score

    # FIX CONV-3: détection convergence + flag passé à risk_manager
    is_convergence = False
    if token_id and condition_id and timestamp > 0:
        try:
            conv_signal = await convergence_detector.process_trade(
                wallet=wallet_address,
                token_id=token_id,
                condition_id=condition_id,
                side=side,
                amount=amount,
                price=price,
                timestamp=timestamp,
            )
            if conv_signal:
                is_convergence = True
                logger.info(
                    f"[CONV] {conv_signal.strength} — "
                    f"{conv_signal.wallet_count} insiders on {token_id[:16]}... "
                    f"conf={conv_signal.confidence:.0%}"
                )
                await notifier.notify_convergence({
                    "count":        conv_signal.wallet_count,
                    "question":     token_id,
                    "condition_id": condition_id,
                    "wallets":      conv_signal.wallets,
                    "side":         side,
                    "avg_price":    conv_signal.avg_price,
                })
        except Exception as e:
            logger.warning(f"[CONV] process_trade error: {e}")

    f = conv_filter.evaluate(
        source_amount=amount,
        price=price,
        wallet_score=effective_score,
        market_id=condition_id,
        consecutive_losses=consecutive_losses,
        entry_timing_score=entry_timing_score,
    )
    if not f.passed:
        return

    decision = risk_manager.evaluate(
        token_id=token_id, price=price,
        source_amount=amount, wallet_win_rate=effective_score,
        is_convergence_signal=is_convergence,
    )
    if not decision.approved:
        logger.debug(f"[RISK] Skipped {token_id[:8]}: {decision.reason}")
        return

    if position_manager.is_open(token_id):
        logger.debug(f"[POS] Already open: {token_id[:8]}")
        return

    market_info = await client.get_market_info(condition_id) if condition_id else None
    question    = market_info.get("question", "") if market_info else ""

    sizer.sync_capital(risk_manager)
    size = sizer.calculate(yes_price=price, conviction_score=f.score, source_amount=amount)
    logger.debug(f"[SIZE] {size.rationale}")

    copied_trade = await engine.copy_trade(
        source_wallet=wallet_address, token_id=token_id,
        side=side, price=price, source_amount=size.amount_usdc,
        market_question=question, market_id=condition_id,
    )

    if copied_trade:
        try:
            risk_manager.register_position(copied_trade.token_id)
        except Exception as e:
            logger.debug(f"[RISK] register_position error: {e}")

        health_monitor.record_trade()
        try:
            position_manager.register(
                trade_id=copied_trade.id or 0,
                token_id=copied_trade.token_id,
                entry_price=copied_trade.price,
                amount_usdc=copied_trade.amount_usdc,
                side=copied_trade.side,
                market_question=copied_trade.market_question or "",
            )
        except Exception as e:
            logger.debug(f"[POS] register error: {e}")
        try:
            await performance_tracker.record_trade(copied_trade)
        except Exception as e:
            logger.warning(f"[PERF] record_trade failed: {e}")
        await notifier.notify_trade(copied_trade, market_question=question)


# ────────────────────────────────────────────────────────────────────────────
async def whale_exit_monitor_loop(
    whale_exit_monitor: WhaleExitMonitor,
    notifier: TelegramNotifier,
    check_interval_sec: int = 300,  # 5 minutes
) -> None:
    """Background task to monitor whale exits.
    
    Checks tracked whales for REDEEM/SELL events every 5 minutes.
    Sends alerts when whales exit markets we're holding.
    
    Note: WHALE_AUTO_EXIT is intentionally not implemented here.
    Auto-closing positions based on whale exits is too risky and could
    lead to losses if the whale exits for reasons unrelated to market outcome.
    Manual review via Telegram alerts is the recommended approach.
    """
    logger.info(f"[WHALE_EXIT] Monitor started — check every {check_interval_sec}s")
    
    while True:
        try:
            await asyncio.sleep(check_interval_sec)
            
            if not settings.whale_exit_tracking:
                continue
            
            # Get tracked whale addresses
            with get_db() as db:
                whales = db.query(TrackedWallet).filter(
                    TrackedWallet.is_whale == True,
                    TrackedWallet.is_active == True,
                ).all()
                
                whale_addresses = [w.address for w in whales]
            
            if not whale_addresses:
                continue
            
            # Check for exits in the last N hours
            exit_events = await whale_exit_monitor.check_whale_exits(
                whale_addresses=whale_addresses,
                since_hours=settings.whale_exit_window_hours,
            )
            
            if not exit_events:
                continue
            
            # Process exits
            for event in exit_events:
                # Log all exits
                logger.info(
                    f"[WHALE_EXIT] {event.wallet[:10]}... "
                    f"{event.exit_type} ${event.amount_usdc:,.0f} @ {event.price:.2f} | "
                    f"{event.title[:45]}"
                )
                
                # Alert if whale exited a market we hold
                if event.matches_our_position and settings.whale_exit_alert:
                    await notifier.send(
                        f"🚨 <b>WHALE EXIT ALERT</b>\n\n"
                        f"Whale <code>{event.wallet[:10]}...</code> "
                        f"just {event.exit_type.lower()}ed a position you hold:\n\n"
                        f"<b>{event.title}</b>\n\n"
                        f"Exit type: <b>{event.exit_type}</b>\n"
                        f"Price: <code>{event.price:.2f}</code>\n"
                        f"Amount: <code>${event.amount_usdc:,.0f}</code>\n\n"
                        f"💡 <i>Consider reviewing this position. "
                        f"The whale may have information you don't.</i>\n\n"
                        f"⚠️ Auto-exit is disabled for safety. Manual review recommended."
                    )
        
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"[WHALE_EXIT] Monitor loop error: {e}")


# ────────────────────────────────────────────────────────────────────────────
async def main_loop(
    scanner: InsiderScanner,
    whale_tracker: WhaleTracker,
    convergence_detector: ConvergenceDetector,
    arbitrage_scanner: ArbitrageScanner,
    market_scanner: MarketScanner,
    llm_agent: LLMAgent,
    engine: TradingEngine,
    notifier: TelegramNotifier,
    client: PolymarketDataClient,
    risk_manager: RiskManager,
    position_manager: PositionManager,
    performance_tracker: PerformanceTracker,
    conv_filter: ConvictionFilter,
    sizer: PositionSizer,
    health_monitor: HealthMonitor,
    llm_session: aiohttp.ClientSession,
    refresher: WalletRefresher,
) -> None:
    logger.info(f"Main loop started. Interval: {settings.scan_interval}s")

    WHALE_EVERY  = 4
    ARB_EVERY    = 20
    MARKET_EVERY = settings.market_scan_every_n_loops
    LLM_EVERY    = settings.llm_scan_every_n_loops
    PERF_EVERY   = 10
    loop_count   = 0

    while True:
        try:
            loop_count += 1
            health_monitor.record_activity()

            # Phase 1 — Whale scan (throttlé: toutes les WHALE_EVERY boucles)
            if loop_count % WHALE_EVERY == 0:
                for event in await whale_tracker.scan():
                    await notifier.notify_whale_event(
                        wallet=event["wallet"],
                        amount_usdc=event["amount_usdc"],
                        market_question=event["title"],
                        side=event["side"],
                        price=event["price"],
                    )
                
                # FIX MAIN-9: Trigger immediate refresh if wallets were auto-added
                if whale_tracker.last_added_count > 0:
                    logger.info(
                        f"[MAIN] {whale_tracker.last_added_count} new whales auto-added — "
                        f"triggering scanner refresh..."
                    )
                    refresher.trigger_refresh()

            # Phase 2+3 — Insider copy trading + convergence par trade
            with get_db() as db:
                wallets = (
                    db.query(TrackedWallet)
                    .filter(TrackedWallet.is_active == True)  # noqa: E712
                    .order_by(TrackedWallet.score.desc())
                    .all()
                )
                wallet_data = [
                    (
                        w.address,
                        float(w.score or 0.70),
                        int(getattr(w, "consecutive_losses", 0) or 0),
                        float(getattr(w, "entry_timing_score", 0.5) or 0.5),
                    )
                    for w in wallets
                ]

            if not wallet_data:
                logger.debug("No active wallets — waiting for refresher...")
                await asyncio.sleep(settings.scan_interval)
                continue

            async def _safe_get_trades(addr: str) -> list:
                try:
                    return await asyncio.wait_for(
                        scanner.get_new_trades(addr), timeout=6.0
                    )
                except asyncio.TimeoutError:
                    logger.debug(f"[SCAN] Timeout for {addr[:10]}...")
                    return []
                except Exception as e:
                    logger.warning(f"[SCAN] Error {addr[:10]}: {e}")
                    return []

            all_trades = await asyncio.gather(
                *[_safe_get_trades(addr) for addr, _, _, _ in wallet_data],
            )
            for (addr, score, losses, timing), trades in zip(wallet_data, all_trades):
                for trade in trades:
                    try:
                        await process_new_trade(
                            trade=trade,
                            wallet_address=addr,
                            wallet_score=score,
                            consecutive_losses=losses,
                            entry_timing_score=timing,
                            engine=engine, notifier=notifier, client=client,
                            risk_manager=risk_manager, position_manager=position_manager,
                            performance_tracker=performance_tracker,
                            conv_filter=conv_filter, sizer=sizer,
                            health_monitor=health_monitor,
                            convergence_detector=convergence_detector,
                        )
                    except Exception as e:
                        logger.error(
                            f"[MAIN] process_new_trade error "
                            f"({addr[:10]} {trade.get('asset', '?')[:12]}): {e}"
                        )

            # Phase 4 — Arbitrage cross-platform
            if loop_count % ARB_EVERY == 0:
                for opp in (await arbitrage_scanner.scan())[:5]:
                    logger.info(f"[ARB] +{opp.profit_pct:.1%} | {opp.direction} | {opp.poly_question[:45]}")
                    await notifier.notify_arbitrage(opp)

            # Phase 5 — Market scan haute échelle
            if loop_count % MARKET_EVERY == 0:
                sigs = await market_scanner.scan_all(max_markets=settings.market_scan_max_markets)
                arbs = [s for s in sigs if s.signal_type == "INTERNAL_ARB"]
                if arbs:
                    logger.info(
                        f"[SCANNER] {len(arbs)} internal arb — top: "
                        f"{arbs[0].question[:50]} (spread={arbs[0].spread:.3f})"
                    )

            # Phase 6 — LLM analysis
            if loop_count % LLM_EVERY == 0 and llm_agent.is_enabled():
                try:
                    async with llm_session.get(
                        f"{settings.polymarket_gamma_host}/markets",
                        params={
                            "active": "true", "closed": "false",
                            "limit": settings.llm_top_markets * 4,
                        },
                    ) as resp:
                        if resp.status == 200:
                            hot = await resp.json()
                            if isinstance(hot, list):
                                for sig in await llm_agent.batch_analyze(
                                    hot, top_n=settings.llm_top_markets
                                ):
                                    logger.info(
                                        f"[LLM] {sig.recommendation} '{sig.question[:45]}' "
                                        f"conf={sig.confidence:.0%} misprice={sig.mispricing_pct:.1%}"
                                    )
                                    await notifier.notify_llm_signal(sig)
                except Exception as e:
                    logger.debug(f"[LLM] Scan cycle error: {e}")

            # Phase 7 — Performance report
            if loop_count % PERF_EVERY == 0:
                try:
                    stats = await performance_tracker.get_summary()
                    logger.info(
                        f"[PERF] WR={stats.get('win_rate', 0):.1%} | "
                        f"PnL={stats.get('total_pnl_usdc', 0):+.2f} USDC | "
                        f"Trades={stats.get('total_trades', 0)} | "
                        f"Open={risk_manager.open_positions_count()}"
                    )
                except Exception as e:
                    logger.debug(f"[PERF] summary error: {e}")

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Main loop error: {e}")

        await asyncio.sleep(settings.scan_interval)


# ────────────────────────────────────────────────────────────────────────────
async def run() -> None:
    logger.info("=" * 62)
    logger.info("  PolyInsider Bot v3.3")
    logger.info("  Copy · Whale · WhaleExit · Conv · Arb · Scanner · LLM · ExitMgr")
    logger.info(f"  Mode : {'DRY RUN 🟡' if settings.dry_run else 'LIVE 🟢'}")
    logger.info(f"  LLM  : {'ENABLED 🧠' if settings.llm_enabled else 'disabled'}")
    logger.info(f"  Arb  : {'ENABLED ⚡' if settings.arb_enabled else 'disabled'}")
    logger.info("  Losing streak protection: ON 🛡️")
    logger.info("  Entry timing filter:      ON ⏱️")
    logger.info("  Partial TP sell (50/50):  ON 💰")
    logger.info("  Telegram commands:        ON 📱")
    logger.info("  Health monitor:           ON 🟩")
    logger.info("  Capital persistence:      ON 💾")
    logger.info("  Sizer capital sync:       ON 🔄")
    logger.info("  Convergence boost (x1.5): ON 🔥")
    # v3.2
    logger.info("  ✨ Trailing Stop-Loss:     ON 📈 (activates @ +15% gain)")
    logger.info("  ✨ Auto Wallet Discovery:  ON 🔍 (every 24h)")
    logger.info("  ✨ Auto-Refresh on Whale:  ON ⚡ (immediate scanner update)")
    # NEW v3.3
    if settings.whale_exit_tracking:
        logger.info(f"  ✨ Whale Exit Tracking:    ON 🚪 (window={settings.whale_exit_window_hours}h)")
        if settings.whale_exit_alert:
            logger.info("     └─ Exit Alerts: ENABLED 🔔")
        if settings.whale_auto_exit:
            logger.info("     └─ Auto-Exit: Config enabled but NOT IMPLEMENTED (too risky)")
    else:
        logger.info("  Whale Exit Tracking:      OFF")
    
    if settings.tiered_multipliers:
        logger.info(f"  Tiered multipliers:       ON 📐 ({settings.tiered_multipliers[:40]})")
    else:
        logger.info("  Tiered multipliers:       OFF (Kelly pur) — /setcapital pour activer")
    if settings.wallet_whitelist:
        logger.info(f"  Whitelist: {len(settings.get_whitelist())} wallets")
    if settings.wallet_blacklist:
        logger.info(f"  Blacklist: {len(settings.get_blacklist())} wallets")
    logger.info("=" * 62)

    init_db()

    client               = PolymarketDataClient()
    notifier             = TelegramNotifier()
    risk_manager         = RiskManager()
    engine               = TradingEngine(risk_manager=risk_manager)
    scanner              = InsiderScanner(client=client)
    whale_tracker        = WhaleTracker(client=client)
    whale_exit_monitor   = WhaleExitMonitor(client=client)  # NEW v3.3
    convergence_detector = ConvergenceDetector(client=client)
    arbitrage_scanner    = ArbitrageScanner(min_profit_pct=settings.arb_min_profit_pct)
    market_scanner       = MarketScanner(max_concurrent=8)
    llm_agent            = LLMAgent()
    performance_tracker  = PerformanceTracker()
    conv_filter          = ConvictionFilter()
    sizer                = PositionSizer()
    position_manager     = PositionManager(
        client=client,
        risk_manager=risk_manager,
        notifier=notifier,
    )
    exit_manager = ExitManager(
        risk_manager=risk_manager,
        notifier=notifier,
        engine=engine,
    )
    health_monitor = HealthMonitor(
        notifier=notifier,
        silence_threshold_min=settings.health_silence_threshold_min,
        check_interval_sec=settings.health_check_interval_sec,
        alert_cooldown_min=settings.health_alert_cooldown_min,
    )
    cmd_handler = BotCommandHandler(
        notifier=notifier,
        risk_manager=risk_manager,
        performance_tracker=performance_tracker,
        sizer=sizer,
    )

    wallet_scanner = WalletScanner(
        client=client,
        insider_scanner=scanner,
    )
    refresher = WalletRefresher(
        scanner=scanner,
        notifier=notifier,
        interval_minutes=60,
        wallet_scanner=wallet_scanner,
    )
    
    features_manager = get_features_manager(
        enable_trailing_sl=True,
        enable_wallet_discovery=True,
    )

    await notifier.notify_startup(dry_run=settings.dry_run)

    stop_event = asyncio.Event()
    loop       = asyncio.get_running_loop()

    def _on_signal(signum, frame) -> None:  # noqa: ARG001
        logger.info("Shutdown signal received — stopping gracefully...")
        loop.call_soon_threadsafe(stop_event.set)

    signal.signal(signal.SIGINT, _on_signal)
    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, _on_signal)

    await refresher.start()
    await exit_manager.start()
    await health_monitor.start()
    await features_manager.start()
    
    try:
        await cmd_handler.start_polling()
    except Exception as e:
        logger.warning(f"[COMMANDS] Could not start polling (token invalid?): {e}")

    llm_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))

    # NEW v3.3: Start whale exit monitor background task
    whale_exit_task = None
    if settings.whale_exit_tracking:
        whale_exit_task = asyncio.create_task(
            whale_exit_monitor_loop(
                whale_exit_monitor=whale_exit_monitor,
                notifier=notifier,
                check_interval_sec=300,  # 5 minutes
            )
        )

    main_task = asyncio.create_task(
        main_loop(
            scanner=scanner, whale_tracker=whale_tracker,
            convergence_detector=convergence_detector,
            arbitrage_scanner=arbitrage_scanner, market_scanner=market_scanner,
            llm_agent=llm_agent, engine=engine, notifier=notifier, client=client,
            risk_manager=risk_manager, position_manager=position_manager,
            performance_tracker=performance_tracker,
            conv_filter=conv_filter, sizer=sizer,
            health_monitor=health_monitor,
            llm_session=llm_session,
            refresher=refresher,
        )
    )

    await stop_event.wait()
    main_task.cancel()
    if whale_exit_task:
        whale_exit_task.cancel()
    
    try:
        await main_task
    except asyncio.CancelledError:
        pass
    
    if whale_exit_task:
        try:
            await whale_exit_task
        except asyncio.CancelledError:
            pass

    await asyncio.gather(
        refresher.stop(),
        exit_manager.stop(),
        health_monitor.stop(),
        features_manager.stop(),
        cmd_handler.stop(),
        client.close(),
        engine.close(),
        arbitrage_scanner.close(),
        market_scanner.close(),
        llm_agent.close(),
        return_exceptions=True,
    )
    if not llm_session.closed:
        await llm_session.close()
    await notifier.send("🛑 <b>PolyInsider Bot stopped.</b>")
    logger.info("Cleanup done. Goodbye!")


if __name__ == "__main__":
    asyncio.run(run())
