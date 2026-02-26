"""
Polymarket Profile Service
============================
Récupère le nom d'utilisateur et l'avatar d'un wallet
depuis l'API publique Polymarket.

Endpoints utilisés:
  GET https://api.polymarket.com/profiles?address=0x...
  → { username, displayName, pfpUrl, bio }

Caching TTL: 5 minutes (évite flood API Polymarket).
"""
from __future__ import annotations

import asyncio
import time
from typing import Optional

import httpx

from bot.utils.logger import logger

# Cache en mémoire: address → (timestamp, profile_data)
_profile_cache: dict[str, tuple[float, dict]] = {}
CACHE_TTL = 300  # 5 minutes


async def fetch_polymarket_profile(address: str) -> dict:
    """
    Retourne le profil Polymarket d'une adresse wallet.

    Returns:
        {
            "username": str | None,
            "display_name": str | None,
            "pfp_url": str | None,
            "polymarket_url": str,
        }
    """
    address_lower = address.lower()

    # Check cache
    if address_lower in _profile_cache:
        ts, cached = _profile_cache[address_lower]
        if time.time() - ts < CACHE_TTL:
            return cached

    profile = {
        "username": None,
        "display_name": None,
        "pfp_url": None,
        "polymarket_url": f"https://polymarket.com/profile/{address_lower}",
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Endpoint 1: profiles API
            resp = await client.get(
                "https://api.polymarket.com/profiles",
                params={"address": address_lower},
            )
            if resp.status_code == 200:
                data = resp.json()

                # L'API peut retourner un objet ou une liste
                if isinstance(data, list) and len(data) > 0:
                    data = data[0]

                if isinstance(data, dict):
                    profile["username"] = (
                        data.get("username")
                        or data.get("name")
                        or data.get("pseudonym")
                        or None
                    )
                    profile["display_name"] = (
                        data.get("displayName")
                        or data.get("display_name")
                        or profile["username"]
                    )
                    profile["pfp_url"] = (
                        data.get("pfpUrl")
                        or data.get("avatar")
                        or data.get("profileImage")
                        or None
                    )

    except httpx.TimeoutException:
        logger.debug(f"[PROFILE] Timeout fetching profile for {address[:10]}...")
    except Exception as e:
        logger.debug(f"[PROFILE] Error fetching profile for {address[:10]}...: {e}")

    # Cache le résultat (même si vide, évite de re-requêter)
    _profile_cache[address_lower] = (time.time(), profile)
    return profile


async def enrich_wallets_with_profiles(wallets: list[dict]) -> list[dict]:
    """
    Enrichit une liste de wallets avec les profils Polymarket en parallèle.
    Safe: ne plante jamais, fallback sur adresse courte si erreur.
    """
    tasks = [fetch_polymarket_profile(w["address"]) for w in wallets]
    profiles = await asyncio.gather(*tasks, return_exceptions=True)

    for wallet, profile in zip(wallets, profiles):
        if isinstance(profile, Exception) or not isinstance(profile, dict):
            profile = {
                "username": None,
                "display_name": None,
                "pfp_url": None,
                "polymarket_url": f"https://polymarket.com/profile/{wallet['address'].lower()}",
            }

        addr = wallet["address"]
        wallet["polymarket_username"] = profile.get("username")
        wallet["polymarket_display_name"] = profile.get("display_name")
        wallet["polymarket_pfp"] = profile.get("pfp_url")
        wallet["polymarket_url"] = profile.get(
            "polymarket_url",
            f"https://polymarket.com/profile/{addr.lower()}"
        )

    return wallets
