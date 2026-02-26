from fastapi import APIRouter
from datetime import datetime

router = APIRouter()

@router.get("/dashboard")
async def get_dashboard():
    """Dashboard endpoint with mock data for testing cockpit v3.1"""
    return {
        "liveStatus": {
            "botActive": True,
            "totalPnL": 1248.50,
            "dailyPnL": 89.30,
            "rpcLatency": 42,
            "gasPrice": 35,
            "walletBalance": 5600.00,
            "lastTradeTimestamp": int(datetime.now().timestamp()) - 180
        },
        "targets": [
            {
                "address": "0xabc123def456789",
                "name": "ProTrader.eth",
                "winrate": 68.4,
                "roi7d": 12.3,
                "volume24h": 8450,
                "avgPositionSize": 600,
                "lastTradeAge": 120,
                "isActive": True,
                "riskAlert": False
            },
            {
                "address": "0x789fedcba654321",
                "name": "WhaleBot",
                "winrate": 72.1,
                "roi7d": 18.7,
                "volume24h": 15200,
                "avgPositionSize": 1200,
                "lastTradeAge": 45,
                "isActive": True,
                "riskAlert": False
            },
            {
                "address": "0x456abc789def012",
                "name": "InsiderAlpha",
                "winrate": 55.2,
                "roi7d": -3.4,
                "volume24h": 3200,
                "avgPositionSize": 400,
                "lastTradeAge": 3600,
                "isActive": False,
                "riskAlert": True
            }
        ],
        "positions": [
            {
                "id": "pos_001",
                "market": "Trump wins 2024 Presidential Election",
                "side": "YES",
                "entryPrice": 0.68,
                "currentPrice": 0.72,
                "pnl": 18.00,
                "probability": 0.71,
                "ageSeconds": 7200,
                "slippage": 0.3,
                "canCashOut": True
            },
            {
                "id": "pos_002",
                "market": "Bitcoin > $100k in Q1 2026",
                "side": "NO",
                "entryPrice": 0.34,
                "currentPrice": 0.39,
                "pnl": -12.50,
                "probability": 0.61,
                "ageSeconds": 300,
                "slippage": 1.2,
                "canCashOut": True
            },
            {
                "id": "pos_003",
                "market": "Fed cuts rates in March 2026",
                "side": "YES",
                "entryPrice": 0.52,
                "currentPrice": 0.48,
                "pnl": -8.00,
                "probability": 0.48,
                "ageSeconds": 86400,
                "slippage": 0.8,
                "canCashOut": True
            }
        ],
        "riskSettings": {
            "positionSizing": {"mode": "fixed", "amount": 500},
            "maxSlippage": 2.0,
            "gasLimit": 100,
            "stopLoss": {"enabled": True, "dailyLimit": -200, "perTrade": -15}
        },
        "alerts": [
            {
                "timestamp": int(datetime.now().timestamp()) - 60,
                "level": "success",
                "message": "TRADE EXECUTED: Bought YES 'Trump wins' $500 @0.68 (slippage 0.3%)"
            },
            {
                "timestamp": int(datetime.now().timestamp()) - 90,
                "level": "warning",
                "message": "GAS SPIKE: 120 gwei detected, trade skipped (config: 100 max)"
            },
            {
                "timestamp": int(datetime.now().timestamp()) - 120,
                "level": "error",
                "message": "RPC TIMEOUT: Infura latency 450ms, switching to Alchemy"
            },
            {
                "timestamp": int(datetime.now().timestamp()) - 150,
                "level": "success",
                "message": "PROFIT: Sold NO 'Fed cuts' $650 (+$48, +7.9%)"
            },
            {
                "timestamp": int(datetime.now().timestamp()) - 200,
                "level": "error",
                "message": "STOP-LOSS: Auto-sold YES 'BTC >100k' -$75 (-15.2%)"
            }
        ]
    }
