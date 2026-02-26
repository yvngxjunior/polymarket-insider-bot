"""
API Route: /api/wallets
========================
Liste les wallets trackés avec enrichissement Polymarket (username + lien profil).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.deps import get_db_session
from api.services.polymarket_profile import enrich_wallets_with_profiles
from bot.database import TrackedWallet

router = APIRouter()


@router.get("/wallets")
async def get_wallets(
    active_only: bool = Query(False, description="Retourner seulement les wallets actifs"),
    db: Session = Depends(get_db_session),
):
    """
    Retourne la liste des wallets trackés.
    Enrichit chaque wallet avec le profil Polymarket (username, lien, avatar).
    Les profils sont cachés 5 minutes pour éviter le flood de l'API Polymarket.
    """
    query = db.query(TrackedWallet)
    if active_only:
        query = query.filter(TrackedWallet.is_active == True)  # noqa: E712

    wallets = query.order_by(
        TrackedWallet.score.desc(),
        TrackedWallet.win_rate.desc(),
    ).all()

    # Sérialise en dict
    wallets_data = [
        {
            "address": w.address,
            "label": w.label,
            "score": float(w.score or 0),
            "win_rate": float(w.win_rate or 0),
            "total_trades": int(w.total_trades or 0),
            "total_profit_usd": float(w.total_profit_usd or 0),
            "is_active": bool(w.is_active),
            "is_whale": bool(w.is_whale),
            "consecutive_losses": int(w.consecutive_losses or 0),
            "entry_timing_score": float(w.entry_timing_score or 0),
            "first_seen": w.first_seen.isoformat() if w.first_seen else None,
            "last_activity": w.last_activity.isoformat() if w.last_activity else None,
            # Enrichissement Polymarket (rempli ci-dessous)
            "polymarket_username": None,
            "polymarket_display_name": None,
            "polymarket_pfp": None,
            "polymarket_url": f"https://polymarket.com/profile/{w.address.lower()}",
        }
        for w in wallets
    ]

    # Enrichit avec les profils Polymarket en parallèle
    wallets_data = await enrich_wallets_with_profiles(wallets_data)

    active_count = sum(1 for w in wallets_data if w["is_active"])

    return {
        "wallets": wallets_data,
        "total_count": len(wallets_data),
        "active_count": active_count,
    }


@router.get("/wallets/{address}/profile")
async def get_wallet_profile(address: str):
    """
    Retourne le profil Polymarket d'un wallet spécifique.
    Utile pour un refresh manuel depuis le dashboard.
    """
    from api.services.polymarket_profile import fetch_polymarket_profile
    profile = await fetch_polymarket_profile(address)
    return profile
