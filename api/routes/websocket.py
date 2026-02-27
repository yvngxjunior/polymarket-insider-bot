from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List
import asyncio
import json
from datetime import datetime

from bot.database import SessionLocal, TrackedWallet, CopiedTrade, PortfolioSnapshot
from bot.utils.logger import logger

router = APIRouter()

# Active WebSocket connections
active_connections: List[WebSocket] = []

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"[WS] Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"[WS] Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Send message to all connected clients"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                disconnected.append(connection)
        
        # Clean up dead connections
        for conn in disconnected:
            try:
                self.active_connections.remove(conn)
            except:
                pass

manager = ConnectionManager()

@router.websocket("/ws/dashboard")
async def websocket_dashboard(websocket: WebSocket):
    """WebSocket endpoint for real-time dashboard updates"""
    await manager.connect(websocket)
    
    try:
        while True:
            # Fetch fresh data from DB
            db = SessionLocal()
            try:
                now = datetime.utcnow()
                
                # Portfolio
                portfolio = db.query(PortfolioSnapshot).filter(PortfolioSnapshot.id == 1).first()
                total_capital = portfolio.total_capital if portfolio else 500.0
                daily_pnl = portfolio.daily_pnl if portfolio else 0.0
                
                # Last trade
                last_trade = db.query(CopiedTrade).order_by(CopiedTrade.created_at.desc()).first()
                last_trade_ts = int(last_trade.created_at.timestamp()) if last_trade else int(now.timestamp()) - 3600
                
                # Mock RPC/Gas (TODO: real monitoring)
                rpc_latency = 42
                gas_price = 35
                
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
            finally:
                db.close()
            
            # Wait 1 second before next update
            await asyncio.sleep(1)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"[WS] Connection error: {e}")
        manager.disconnect(websocket)
