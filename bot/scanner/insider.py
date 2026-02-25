import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from bot.config import get_settings
from bot.database import get_db, TrackedWallet
from bot.trading.polymarket import PolymarketDataClient
from bot.utils.helpers import score_wallet, get_score_label
from bot.utils.logger import logger

settings = get_settings()

# AMÉLIORATION: Décroissance temporelle — les trades récents comptent davantage
# Un trade vieux de 30 jours n'a qu'un poids de ~50%
DECAY_HALF_LIFE_DAYS = 30


@dataclass
class WalletAnalysis:
    address: str
    win_rate: float              # Win rate brut
    win_rate_weighted: float     # ✨ NEW: Win rate pondéré par récence
    total_trades: int
    total_profit_usd: float
    avg_profit_per_trade: float  # ✨ NEW: Profit moyen par trade
    score: float
    score_label: str
    is_qualified: bool
    consecutive_losses: int      # ✨ NEW: Séries de pertes consécutives
    entry_timing_score: float    # ✨ NEW: Score 0-1 sur la qualité du timing d'entrée
    latest_trade: Optional[dict] = None
    disqualify_reason: str = ""


def _decay_weight(trade_timestamp: Optional[str]) -> float:
    """
    Calcule le poids d'un trade selon son ancienneté.
    Formule: w = 0.5 ^ (age_days / HALF_LIFE)
    → Trade d'aujourd'hui = 1.0, trade de 30j = 0.5, trade de 60j = 0.25
    """
    if not trade_timestamp:
        return 0.5
    try:
        ts = datetime.fromisoformat(trade_timestamp.replace("Z", "+00:00"))
        age_days = (datetime.now().astimezone() - ts).days
        return 0.5 ** (age_days / DECAY_HALF_LIFE_DAYS)
    except Exception:
        return 0.5


class InsiderScanner:
    """
    Détecte les wallets à haut win-rate (insiders potentiels).

    AMÉLIORATIONS v2:
      - Win rate pondéré par récence (évite de copier un wallet qui gagnait il y a 3 mois)
      - Suivi des séries de pertes consécutives (stop automatique si wallet en losing streak)
      - Score de timing d'entrée (les bons insiders entrent tôt, pas à 95%)
      - Profit moyen par trade (filtre les wallets qui gagnent souvent mais peu)
    """

    def __init__(self, client: PolymarketDataClient):
        self.client = client
        self._known_trades: dict[str, set[str]] = {}

    async def analyze_wallet(self, wallet_address: str) -> WalletAnalysis:
        """Analyse complète d'un wallet avec scoring amélioré."""
        trades = await self.client.get_wallet_trades(wallet_address, limit=300)

        if not trades:
            return self._empty_analysis(wallet_address, "No trade history")

        resolved = [t for t in trades if t.get("type") in ("REDEEM", "SELL")]
        total = len(resolved)

        if total < settings.min_trades_count:
            return self._empty_analysis(
                wallet_address,
                f"Not enough trades ({total} < {settings.min_trades_count})"
            )

        # --- Win rate brut ---
        profitable_trades = [
            t for t in resolved
            if float(t.get("usdcSize", 0)) > float(t.get("tradeSize", 0))
        ]
        win_rate = len(profitable_trades) / total

        # --- ✨ Win rate pondéré par récence ---
        weighted_wins = sum(
            _decay_weight(t.get("timestamp"))
            for t in resolved
            if float(t.get("usdcSize", 0)) > float(t.get("tradeSize", 0))
        )
        total_weight = sum(_decay_weight(t.get("timestamp")) for t in resolved)
        win_rate_weighted = weighted_wins / total_weight if total_weight > 0 else 0

        # --- ✨ Séries de pertes consécutives (sur les 10 derniers trades) ---
        recent = sorted(resolved, key=lambda t: t.get("timestamp", ""), reverse=True)[:10]
        consecutive_losses = 0
        for t in recent:
            if float(t.get("usdcSize", 0)) <= float(t.get("tradeSize", 0)):
                consecutive_losses += 1
            else:
                break

        # --- Profit total & moyen ---
        profits = [
            float(t.get("usdcSize", 0)) - float(t.get("tradeSize", 0))
            for t in resolved
        ]
        total_profit = sum(profits)
        avg_profit = total_profit / total if total > 0 else 0

        # --- ✨ Score de timing d'entrée ---
        # Les bons traders entrent quand le prix est bas (0.1-0.5)
        # = signal d'information avantageuse
        entry_prices = [
            float(t.get("price", 0.5))
            for t in profitable_trades
            if float(t.get("price", 0)) > 0
        ]
        if entry_prices:
            avg_entry = sum(entry_prices) / len(entry_prices)
            # Score élevé = entrées à bas prix (bon timing)
            entry_timing_score = max(0, 1 - (avg_entry / 0.6))
        else:
            entry_timing_score = 0.5

        score = score_wallet(win_rate_weighted, total, total_profit)
        label = get_score_label(score)

        # Disqualifier si losing streak trop longue
        if consecutive_losses >= 5:
            return WalletAnalysis(
                address=wallet_address,
                win_rate=win_rate,
                win_rate_weighted=win_rate_weighted,
                total_trades=total,
                total_profit_usd=total_profit,
                avg_profit_per_trade=avg_profit,
                score=score,
                score_label=label,
                is_qualified=False,
                consecutive_losses=consecutive_losses,
                entry_timing_score=entry_timing_score,
                latest_trade=trades[0] if trades else None,
                disqualify_reason=f"Losing streak: {consecutive_losses} consecutive losses"
            )

        qualified = (
            win_rate_weighted >= settings.min_win_rate
            and avg_profit >= 1.0  # Profit moyen minimum de 1 USDC
        )

        self._known_trades[wallet_address] = {t.get("id", "") for t in trades}

        return WalletAnalysis(
            address=wallet_address,
            win_rate=win_rate,
            win_rate_weighted=win_rate_weighted,
            total_trades=total,
            total_profit_usd=total_profit,
            avg_profit_per_trade=avg_profit,
            score=score,
            score_label=label,
            is_qualified=qualified,
            consecutive_losses=consecutive_losses,
            entry_timing_score=entry_timing_score,
            latest_trade=trades[0] if trades else None,
            disqualify_reason="" if qualified else
                f"WR weighted: {win_rate_weighted:.0%} or avg profit too low (${avg_profit:.2f})"
        )

    async def get_new_trades(self, wallet_address: str) -> list[dict]:
        """Retourne uniquement les trades NOUVEAUX depuis la dernière analyse."""
        trades = await self.client.get_wallet_trades(wallet_address, limit=20)
        known = self._known_trades.get(wallet_address, set())
        new_trades = []
        for trade in trades:
            trade_id = trade.get("id", "")
            if trade_id and trade_id not in known:
                new_trades.append(trade)
                known.add(trade_id)
        self._known_trades[wallet_address] = known
        return new_trades

    async def refresh_tracked_wallets(self) -> list[WalletAnalysis]:
        """Scan global: met à jour tous les wallets suivis en DB."""
        logger.info("Starting full wallet refresh (v2 with decay scoring)...")
        top_traders = await self.client.get_top_traders(limit=300)

        tasks = [
            self.analyze_wallet(trader.get("proxyWalletAddress", ""))
            for trader in top_traders
            if trader.get("proxyWalletAddress")
        ]
        analyses = await asyncio.gather(*tasks, return_exceptions=True)

        results = []
        with get_db() as db:
            for analysis in analyses:
                if isinstance(analysis, Exception):
                    logger.warning(f"Wallet analysis failed: {analysis}")
                    continue
                if not analysis.is_qualified:
                    # Désactiver un wallet précédemment qualifié s'il est maintenant disqualifié
                    existing = db.get(TrackedWallet, analysis.address)
                    if existing and existing.is_active and analysis.consecutive_losses >= 5:
                        existing.is_active = False
                        logger.warning(
                            f"⚠️ Wallet {analysis.address[:8]}... DEACTIVATED — losing streak"
                        )
                    continue

                wallet = db.get(TrackedWallet, analysis.address)
                if wallet is None:
                    wallet = TrackedWallet(address=analysis.address)
                    db.add(wallet)
                    logger.info(f"✨ New insider: {analysis.address[:8]}... {analysis.score_label} "
                                f"| WR: {analysis.win_rate_weighted:.0%} | Avg: ${analysis.avg_profit_per_trade:.1f}")

                wallet.win_rate = analysis.win_rate_weighted  # on stocke le WR pondéré
                wallet.total_trades = analysis.total_trades
                wallet.total_profit_usd = analysis.total_profit_usd
                wallet.score = analysis.score
                wallet.is_active = True
                results.append(analysis)

        logger.info(f"Refresh done. {len(results)} qualified wallets. "
                    f"Top score: {max((a.score for a in results), default=0):.1f}")
        return results

    def _empty_analysis(self, address: str, reason: str) -> WalletAnalysis:
        return WalletAnalysis(
            address=address, win_rate=0, win_rate_weighted=0, total_trades=0,
            total_profit_usd=0, avg_profit_per_trade=0, score=0,
            score_label="🔴 D (Weak)", is_qualified=False,
            consecutive_losses=0, entry_timing_score=0,
            disqualify_reason=reason
        )
