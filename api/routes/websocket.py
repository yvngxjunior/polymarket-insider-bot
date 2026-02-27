from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List
import asyncio
from datetime import datetime
from sqlalchemy import desc

from bot.database import SessionLocal, TrackedWallet, CopiedTrade, PortfolioSnapshot
from bot.utils.logger import logger
from bot.utils.gas_tracker import get_gas_tracker
from bot.utils.rpc_monitor import get_rpc_monitor

router = APIRouter()

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"[WS] Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        try:
            self.active_connections.remove(websocket)
        except:
            pass
        logger.info(f"[WS] Client disconnected. Total: {len(self.active_connections)}")

manager = ConnectionManager()

# Initialize monitors
gas_tracker = get_gas_tracker()
rpc_monitor = get_rpc_monitor("https://polygon-rpc.com")  # Use your Infura/Alchemy URL

@router.websocket("/ws/dashboard")
async def websocket_dashboard(websocket: WebSocket):
    """WebSocket endpoint for real-time dashboard updates"""
    await manager.connect(websocket)
    
    try:
        while True:
            db = SessionLocal()
            try:
                now = datetime.utcnow()
                
                # Portfolio
                portfolio = db.query(PortfolioSnapshot).filter(
                    PortfolioSnapshot.id == 1
                ).first()
                total_capital = portfolio.total_capital if portfolio else 500.0
                daily_pnl = portfolio.daily_pnl if portfolio else 0.0
                
                # Last trade
                last_trade = db.query(CopiedTrade).order_by(
                    desc(CopiedTrade.created_at)
                ).first()
                last_trade_ts = int(last_trade.created_at.timestamp()) if last_trade else int(now.timestamp()) - 3600
                
                # REAL DATA: Fetch gas price and RPC latency
                gas_price_task = asyncio.create_task(gas_tracker.get_gas_price())
                rpc_latency_task = asyncio.create_task(rpc_monitor.ping())
                
                # Wait for both with timeout
                try:
                    gas_price, rpc_latency = await asyncio.wait_for(
                        asyncio.gather(gas_price_task, rpc_latency_task),
                        timeout=3.0
                    )
                except asyncio.TimeoutError:
                    logger.warning("[WS] Monitor timeout, using defaults")
                    gas_price = 35
                    rpc_latency = 50
                
                # Build update message
                update = {
                    "type": "dashboard_update",
                    "timestamp": int(now.timestamp()),
                    "liveStatus": {
                        "botActive": True,
                        "totalPnL": round(total_capital - 500.0, 2),
                        "dailyPnL": round(daily_pnl, 2),
                        "rpcLatency": rpc_latency,
                        "gasPrice": gas_price,
                        "walletBalance": round(total_capital, 2),
                        "lastTradeTimestamp": last_trade_ts
                    }
                }
                
                # Send to this client
                await websocket.send_json(update)
                
            except Exception as e:
                logger.error(f"[WS] Error fetching data: {e}")
                # Send minimal update on error
                await websocket.send_json({
                    "type": "dashboard_update",
                    "timestamp": int(datetime.utcnow().timestamp()),
                    "liveStatus": {
                        "botActive": False,
                        "totalPnL": 0.0,
                        "dailyPnL": 0.0,
                        "rpcLatency": 0,
                        "gasPrice": 0,
                        "walletBalance": 500.0,
                        "lastTradeTimestamp": int(datetime.utcnow().timestamp())
                    }
                })
            finally:
                db.close()
            
            # Wait 1 second before next update
            await asyncio.sleep(1)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"[WS] Connection error: {e}")
        manager.disconnect(websocket)
