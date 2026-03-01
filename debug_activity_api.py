"""Diagnostic script to check /activity API structure.

This script tests if the Polymarket /activity API returns REDEEM events.
Run this to diagnose why all wallets show 0% redeem rate.

Usage:
    python debug_activity_api.py
"""
import asyncio
import json
from collections import defaultdict

from bot.trading.polymarket import PolymarketDataClient
from bot.database import get_db, TrackedWallet
from bot.utils.logger import logger


async def test_activity_api():
    """Test /activity API to see if REDEEM events exist."""
    
    logger.info("="*70)
    logger.info("🔍 DIAGNOSTIC: Testing /activity API structure")
    logger.info("="*70)
    
    client = PolymarketDataClient()
    
    # Get a sample whale from DB
    try:
        with get_db() as db:
            whale = db.query(TrackedWallet).filter(
                TrackedWallet.is_whale == True,
                TrackedWallet.is_active == True,
            ).first()
            
            if not whale:
                logger.error("❌ No tracked whales found in DB")
                return
            
            wallet_address = whale.address
            logger.info(f"📋 Testing wallet: {wallet_address[:10]}...{wallet_address[-6:]}")
    except Exception as e:
        logger.error(f"❌ DB error: {e}")
        return
    
    # Test 1: Get wallet activity
    logger.info("\n" + "="*70)
    logger.info("TEST 1: Fetching wallet activity (limit=100)")
    logger.info("="*70)
    
    try:
        activity = await client.get_wallet_activity(
            wallet=wallet_address,
            limit=100,
        )
        
        logger.info(f"✅ API call successful")
        logger.info(f"📊 Total events returned: {len(activity)}")
        
        if not activity:
            logger.warning("⚠️  No activity returned (empty list)")
            return
        
    except Exception as e:
        logger.error(f"❌ API call failed: {e}")
        return
    
    # Test 2: Analyze event types
    logger.info("\n" + "="*70)
    logger.info("TEST 2: Analyzing event types")
    logger.info("="*70)
    
    event_types = defaultdict(int)
    event_sides = defaultdict(int)
    sample_events = {}
    
    for event in activity:
        event_type = event.get("type", "UNKNOWN").upper()
        event_types[event_type] += 1
        
        # Store first sample of each type
        if event_type not in sample_events:
            sample_events[event_type] = event
        
        # Track sides for TRADE events
        if event_type == "TRADE":
            side = event.get("side", "UNKNOWN").upper()
            event_sides[f"TRADE_{side}"] += 1
    
    logger.info(f"\n📈 Event type distribution:")
    for event_type, count in sorted(event_types.items(), key=lambda x: -x[1]):
        pct = (count / len(activity)) * 100
        logger.info(f"  • {event_type:15} : {count:4} ({pct:.1f}%)")
    
    if event_sides:
        logger.info(f"\n📊 Trade sides:")
        for side, count in sorted(event_sides.items()):
            logger.info(f"  • {side:15} : {count:4}")
    
    # Test 3: Check if REDEEM exists
    logger.info("\n" + "="*70)
    logger.info("TEST 3: REDEEM event detection")
    logger.info("="*70)
    
    if "REDEEM" in event_types:
        logger.info(f"✅ REDEEM events found! Count: {event_types['REDEEM']}")
        logger.info(f"\n📋 Sample REDEEM event structure:")
        logger.info(json.dumps(sample_events["REDEEM"], indent=2))
    else:
        logger.warning("⚠️  NO REDEEM EVENTS FOUND!")
        logger.warning("   This explains why all wallets show 0% redeem rate.")
        logger.warning("   The /activity API may not include REDEEM events.")
    
    # Test 4: Sample event structures
    logger.info("\n" + "="*70)
    logger.info("TEST 4: Sample event structures (first 3)")
    logger.info("="*70)
    
    for i, event in enumerate(activity[:3], 1):
        logger.info(f"\n📄 Event #{i}:")
        # Pretty print with key info
        event_type = event.get("type", "?")
        timestamp = event.get("timestamp", "?")
        side = event.get("side", "N/A")
        price = event.get("price", "N/A")
        usdc_size = event.get("usdcSize", "N/A")
        
        logger.info(f"  Type      : {event_type}")
        logger.info(f"  Timestamp : {timestamp}")
        logger.info(f"  Side      : {side}")
        logger.info(f"  Price     : {price}")
        logger.info(f"  USDC Size : {usdc_size}")
        logger.info(f"  All keys  : {list(event.keys())}")
    
    # Test 5: Try event_type filter
    logger.info("\n" + "="*70)
    logger.info("TEST 5: Testing event_type='REDEEM' filter")
    logger.info("="*70)
    
    try:
        redeem_activity = await client.get_wallet_activity(
            wallet=wallet_address,
            limit=50,
            event_type="REDEEM",
        )
        
        if redeem_activity:
            logger.info(f"✅ Filtered REDEEM call successful")
            logger.info(f"📊 REDEEM events returned: {len(redeem_activity)}")
            
            if len(redeem_activity) > 0:
                logger.info(f"\n📋 First REDEEM event:")
                logger.info(json.dumps(redeem_activity[0], indent=2))
        else:
            logger.warning("⚠️  No REDEEM events returned with filter")
    
    except Exception as e:
        logger.warning(f"⚠️  Filtered call failed (may not be supported): {e}")
    
    # Test 6: Alternative data sources
    logger.info("\n" + "="*70)
    logger.info("TEST 6: Checking alternative methods")
    logger.info("="*70)
    
    # Try get_market_activity with a known condition_id
    try:
        # Get a condition_id from recent activity
        if activity:
            condition_id = activity[0].get("conditionId")
            if condition_id:
                logger.info(f"Testing get_market_activity for condition: {condition_id[:20]}...")
                
                market_activity = await client.get_market_activity(
                    condition_id=condition_id,
                    limit=50,
                )
                
                if market_activity:
                    market_event_types = defaultdict(int)
                    for event in market_activity:
                        event_type = event.get("type", "UNKNOWN").upper()
                        market_event_types[event_type] += 1
                    
                    logger.info(f"✅ Market activity fetched: {len(market_activity)} events")
                    logger.info(f"📊 Market event types: {dict(market_event_types)}")
                    
                    if "REDEEM" in market_event_types:
                        logger.info("✅ REDEEM found in market activity!")
                        logger.info("💡 Solution: Use market_activity instead of wallet_activity for REDEEM detection")
                    else:
                        logger.warning("⚠️  No REDEEM in market activity either")
    except Exception as e:
        logger.warning(f"⚠️  Market activity test failed: {e}")
    
    # Final summary
    logger.info("\n" + "="*70)
    logger.info("📋 DIAGNOSTIC SUMMARY")
    logger.info("="*70)
    
    has_redeem = "REDEEM" in event_types
    has_trade = "TRADE" in event_types
    
    logger.info(f"\n✅ API Working: YES")
    logger.info(f"📊 Total events: {len(activity)}")
    logger.info(f"🔄 TRADE events: {'YES' if has_trade else 'NO'}")
    logger.info(f"🎁 REDEEM events: {'YES ✅' if has_redeem else 'NO ❌'}")
    
    if not has_redeem:
        logger.warning("\n⚠️  REDEEM EVENTS NOT FOUND IN API")
        logger.warning("\n🔧 Recommended fixes:")
        logger.warning("   1. Check if Polymarket has a separate /redeems endpoint")
        logger.warning("   2. Use market resolution data to infer redeems")
        logger.warning("   3. Calculate win rate from BUY price vs final resolution")
        logger.warning("   4. Focus on SELL timing analysis instead of REDEEM detection")
    else:
        logger.info("\n✅ REDEEM events are available in the API!")
        logger.info("   The parsing logic in whale_exit_monitor.py should work correctly.")
    
    await client.close()
    logger.info("\n" + "="*70)
    logger.info("✅ Diagnostic complete")
    logger.info("="*70)


if __name__ == "__main__":
    asyncio.run(test_activity_api())
