"""
Unit tests — WalletScanner + WalletRefresher
Zéro appels API réels: InsiderScanner, PolymarketDataClient et TelegramNotifier sont mockés.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.scanner.wallet_scanner import DiscoveryResult, WalletScanner
from bot.scanner.wallet_refresher import WalletRefresher
from bot.scanner.insider import WalletAnalysis


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_analysis(
    address: str = "0xWallet001",
    win_rate: float = 0.75,
    total_trades: int = 40,
    total_profit: float = 800.0,
    is_qualified: bool = True,
    consecutive_losses: int = 0,
) -> WalletAnalysis:
    return WalletAnalysis(
        address=address,
        win_rate=win_rate,
        win_rate_weighted=win_rate,
        total_trades=total_trades,
        total_profit_usd=total_profit,
        avg_profit_per_trade=total_profit / max(total_trades, 1),
        score=0.75,
        score_label="🟢 B",
        is_qualified=is_qualified,
        consecutive_losses=consecutive_losses,
        entry_timing_score=0.6,
    )


def make_insider_scanner(analyses: list[WalletAnalysis] | None = None) -> MagicMock:
    scanner = MagicMock()
    scanner.client = MagicMock()
    scanner.client.get_top_traders = AsyncMock(return_value=[
        {"proxyWalletAddress": f"0xTrader{i:03d}"} for i in range(3)
    ])
    scanner.client.get_recent_large_trades = AsyncMock(return_value=[
        {"maker": "0xWhale001", "usdcSize": 600.0}
    ])
    scanner.analyze_wallet = AsyncMock(side_effect=lambda addr: make_analysis(address=addr))
    scanner.refresh_tracked_wallets = AsyncMock(
        return_value=analyses or [make_analysis()]
    )
    return scanner


def make_notifier() -> MagicMock:
    notifier = MagicMock()
    notifier.notify_new_insider = AsyncMock()
    return notifier


# ===========================================================================
# WalletScanner
# ===========================================================================

@pytest.mark.asyncio
async def test_discover_returns_discovery_result():
    """discover() doit retourner un DiscoveryResult."""
    scanner = make_insider_scanner()
    with patch("bot.scanner.wallet_scanner.get_db") as mock_db:
        mock_db.return_value.__enter__ = MagicMock(return_value=MagicMock(
            get=MagicMock(return_value=None),
            add=MagicMock(),
        ))
        mock_db.return_value.__exit__ = MagicMock(return_value=False)
        ws = WalletScanner(client=scanner.client, insider_scanner=scanner)
        result = await ws.discover()
    assert isinstance(result, DiscoveryResult)


@pytest.mark.asyncio
async def test_new_qualified_wallet_detected():
    """Un wallet qualifié inexistant en DB doit apparaître dans new_wallets."""
    scanner = make_insider_scanner([make_analysis("0xNew001", is_qualified=True)])
    # Client pour _collect_candidates
    scanner.client.get_top_traders = AsyncMock(return_value=[
        {"proxyWalletAddress": "0xNew001"}
    ])
    scanner.client.get_recent_large_trades = AsyncMock(return_value=[])

    with patch("bot.scanner.wallet_scanner.get_db") as mock_db:
        ctx = MagicMock()
        ctx.get = MagicMock(return_value=None)   # pas en DB
        ctx.add = MagicMock()
        mock_db.return_value.__enter__ = MagicMock(return_value=ctx)
        mock_db.return_value.__exit__ = MagicMock(return_value=False)

        ws = WalletScanner(client=scanner.client, insider_scanner=scanner)
        result = await ws.discover()

    assert "0xNew001" in result.new_wallets


@pytest.mark.asyncio
async def test_unqualified_wallet_not_added():
    """Un wallet non qualifié ne doit pas être ajouté en DB."""
    scanner = make_insider_scanner()
    scanner.analyze_wallet = AsyncMock(
        return_value=make_analysis(is_qualified=False)
    )
    scanner.client.get_top_traders = AsyncMock(return_value=[
        {"proxyWalletAddress": "0xBad001"}
    ])
    scanner.client.get_recent_large_trades = AsyncMock(return_value=[])

    with patch("bot.scanner.wallet_scanner.get_db") as mock_db:
        ctx = MagicMock()
        ctx.get = MagicMock(return_value=None)
        ctx.add = MagicMock()
        mock_db.return_value.__enter__ = MagicMock(return_value=ctx)
        mock_db.return_value.__exit__ = MagicMock(return_value=False)

        ws = WalletScanner(client=scanner.client, insider_scanner=scanner)
        result = await ws.discover()

    ctx.add.assert_not_called()
    assert result.total_qualified == 0


@pytest.mark.asyncio
async def test_deduplication_across_sources():
    """Un wallet présent dans leaderboard ET gros trades ne doit être analysé qu'une fois."""
    dup_addr = "0xDuplicate"
    scanner = make_insider_scanner()
    scanner.client.get_top_traders = AsyncMock(return_value=[
        {"proxyWalletAddress": dup_addr}
    ])
    scanner.client.get_recent_large_trades = AsyncMock(return_value=[
        {"maker": dup_addr, "usdcSize": 600.0}
    ])

    with patch("bot.scanner.wallet_scanner.get_db") as mock_db:
        ctx = MagicMock()
        ctx.get = MagicMock(return_value=None)
        ctx.add = MagicMock()
        mock_db.return_value.__enter__ = MagicMock(return_value=ctx)
        mock_db.return_value.__exit__ = MagicMock(return_value=False)

        ws = WalletScanner(client=scanner.client, insider_scanner=scanner)
        await ws.discover()

    # analyze_wallet doit être appelé UNE seule fois pour cet address
    calls = [c.args[0] for c in scanner.analyze_wallet.call_args_list]
    assert calls.count(dup_addr) == 1


def test_discovery_result_str():
    """__str__ de DiscoveryResult doit être lisible."""
    r = DiscoveryResult(
        new_wallets=["0xA", "0xB"],
        updated_wallets=["0xC"],
        deactivated_wallets=[],
        total_candidates=10,
        total_qualified=3,
    )
    s = str(r)
    assert "+2 new" in s
    assert "3/10 qualified" in s


# ===========================================================================
# WalletRefresher
# ===========================================================================

@pytest.mark.asyncio
async def test_refresher_start_triggers_immediate_refresh():
    """start() doit déclencher un refresh immédiat."""
    scanner = make_insider_scanner()
    notifier = make_notifier()

    with patch("bot.scanner.wallet_refresher.get_db") as mock_db:
        ctx = MagicMock()
        ctx.get = MagicMock(return_value=None)
        mock_db.return_value.__enter__ = MagicMock(return_value=ctx)
        mock_db.return_value.__exit__ = MagicMock(return_value=False)

        refresher = WalletRefresher(
            scanner=scanner, notifier=notifier, interval_seconds=999  # FIX: était interval_minutes
        )
        await refresher.start()
        await asyncio.sleep(0.05)  # laisse le temps au task de s'exécuter
        await refresher.stop()

    scanner.refresh_tracked_wallets.assert_called()


@pytest.mark.asyncio
async def test_new_insider_triggers_notification():
    """Un nouveau wallet (pas encore connu) doit déclencher une notification Telegram."""
    scanner = make_insider_scanner([make_analysis("0xFreshWallet")])
    notifier = make_notifier()

    with patch("bot.scanner.wallet_refresher.get_db") as mock_db:
        ctx = MagicMock()
        ctx.get = MagicMock(return_value=None)
        mock_db.return_value.__enter__ = MagicMock(return_value=ctx)
        mock_db.return_value.__exit__ = MagicMock(return_value=False)

        refresher = WalletRefresher(
            scanner=scanner, notifier=notifier, interval_seconds=999  # FIX: était interval_minutes
        )
        await refresher.start()
        await asyncio.sleep(0.05)
        await refresher.stop()

    notifier.notify_new_insider.assert_called_once()


@pytest.mark.asyncio
async def test_known_wallet_no_duplicate_notification():
    """Un wallet déjà connu ne doit pas déclencher de notification."""
    scanner = make_insider_scanner([make_analysis("0xKnown")])
    notifier = make_notifier()

    with patch("bot.scanner.wallet_refresher.get_db") as mock_db:
        ctx = MagicMock()
        ctx.get = MagicMock(return_value=None)
        mock_db.return_value.__enter__ = MagicMock(return_value=ctx)
        mock_db.return_value.__exit__ = MagicMock(return_value=False)

        refresher = WalletRefresher(
            scanner=scanner, notifier=notifier, interval_seconds=999  # FIX: était interval_minutes
        )
        refresher._known_wallets.add("0xKnown")  # déjà connu
        await refresher.start()
        await asyncio.sleep(0.05)
        await refresher.stop()

    notifier.notify_new_insider.assert_not_called()


@pytest.mark.asyncio
async def test_consecutive_losses_synced_to_db():
    """consecutive_losses doit être mis à jour en DB lors du refresh."""
    wallet_mock = MagicMock()
    wallet_mock.consecutive_losses = 0  # valeur initiale

    scanner = make_insider_scanner([
        make_analysis("0xLosing", consecutive_losses=2)
    ])
    notifier = make_notifier()

    with patch("bot.scanner.wallet_refresher.get_db") as mock_db:
        ctx = MagicMock()
        ctx.get = MagicMock(return_value=wallet_mock)
        mock_db.return_value.__enter__ = MagicMock(return_value=ctx)
        mock_db.return_value.__exit__ = MagicMock(return_value=False)

        refresher = WalletRefresher(
            scanner=scanner, notifier=notifier, interval_seconds=999  # FIX: était interval_minutes
        )
        await refresher.start()
        await asyncio.sleep(0.05)
        await refresher.stop()

    # consecutive_losses doit avoir été mis à jour à 2
    assert wallet_mock.consecutive_losses == 2


@pytest.mark.asyncio
async def test_refresher_stop_cancels_task():
    """stop() doit arrêter proprement le task sans exception."""
    scanner = make_insider_scanner()
    notifier = make_notifier()

    with patch("bot.scanner.wallet_refresher.get_db") as mock_db:
        ctx = MagicMock()
        ctx.get = MagicMock(return_value=None)
        mock_db.return_value.__enter__ = MagicMock(return_value=ctx)
        mock_db.return_value.__exit__ = MagicMock(return_value=False)

        refresher = WalletRefresher(
            scanner=scanner, notifier=notifier, interval_seconds=999  # FIX: était interval_minutes
        )
        await refresher.start()
        await asyncio.sleep(0.02)
        await refresher.stop()  # ne doit pas lever d'exception

    assert refresher._task is None or refresher._task.done()
