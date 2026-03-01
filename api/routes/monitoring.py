from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Optional
import subprocess
import docker
import os
from datetime import datetime, timedelta

from api.database import get_db
from api.models import TradeSignal, MonitoredWallet, Position

router = APIRouter(prefix="/api", tags=["monitoring"])

@router.get("/signals")
async def get_signals(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Get recent trade signals ordered by creation time
    """
    signals = (
        db.query(TradeSignal)
        .join(MonitoredWallet, TradeSignal.wallet_id == MonitoredWallet.id)
        .order_by(desc(TradeSignal.created_at))
        .limit(limit)
        .all()
    )
    
    return [
        {
            "id": s.id,
            "whale_address": s.wallet.address[:8] + "..." + s.wallet.address[-4:],
            "signal_type": s.signal_type,
            "outcome_price": float(s.outcome_price) if s.outcome_price else 0.0,
            "market_name": getattr(s, 'market_question', None),
            "created_at": s.created_at.isoformat()
        }
        for s in signals
    ]

@router.get("/whales")
async def get_whales(
    limit: int = Query(12, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """
    Get top whales ordered by whale_score
    """
    whales = (
        db.query(MonitoredWallet)
        .order_by(desc(MonitoredWallet.whale_score))
        .limit(limit)
        .all()
    )
    
    return [
        {
            "address": w.address,
            "whale_score": float(w.whale_score) if w.whale_score else 0.0,
            "conviction_score": float(w.conviction_score) if w.conviction_score else 0.0,
            "total_pnl": float(w.total_pnl) if w.total_pnl else 0.0,
            "total_volume": float(w.total_volume) if w.total_volume else 0.0,
            "last_updated": w.last_updated.isoformat() if w.last_updated else None
        }
        for w in whales
    ]

@router.get("/logs")
async def get_logs(
    service: str = Query(..., description="Service name: wallet-refresher, executor, db"),
    tail: int = Query(100, ge=10, le=500)
):
    """
    Get Docker service logs
    """
    try:
        # Use docker compose logs command
        result = subprocess.run(
            ["docker", "compose", "logs", "--tail", str(tail), service],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        )
        
        if result.returncode != 0:
            return {"error": f"Failed to get logs: {result.stderr}"}
        
        # Parse logs into structured format
        logs = []
        for line in result.stdout.splitlines()[-tail:]:
            if not line.strip():
                continue
            
            # Try to parse timestamp and level
            parts = line.split()
            if len(parts) >= 3:
                logs.append({
                    "timestamp": parts[0] if len(parts[0]) > 5 else "",
                    "level": parts[1] if parts[1] in ["INFO", "WARNING", "ERROR", "DEBUG"] else "INFO",
                    "message": " ".join(parts[2:] if parts[1] in ["INFO", "WARNING", "ERROR", "DEBUG"] else parts[1:])
                })
            else:
                logs.append({
                    "timestamp": "",
                    "level": "INFO",
                    "message": line
                })
        
        return logs
        
    except subprocess.TimeoutExpired:
        return {"error": "Logs request timed out"}
    except FileNotFoundError:
        return {"error": "Docker compose not found. Make sure Docker is installed."}
    except Exception as e:
        return {"error": f"Failed to retrieve logs: {str(e)}"}

@router.get("/executor/status")
async def get_executor_status():
    """
    Get executor runtime status
    """
    try:
        client = docker.from_env()
        containers = client.containers.list(filters={"name": "executor"})
        
        if not containers:
            return {"status": "stopped", "message": "Executor container not found"}
        
        container = containers[0]
        return {
            "status": container.status,
            "state": container.attrs["State"],
            "started_at": container.attrs["State"].get("StartedAt"),
            "finished_at": container.attrs["State"].get("FinishedAt")
        }
        
    except docker.errors.DockerException as e:
        return {"status": "unknown", "error": str(e)}
    except Exception as e:
        return {"status": "unknown", "error": str(e)}

@router.get("/health/detailed")
async def health_detailed():
    """
    Enhanced health check with Docker container statuses
    """
    try:
        client = docker.from_env()
        all_containers = client.containers.list(all=True)
        
        services = {
            "wallet_refresher": "stopped",
            "executor": "stopped",
            "db": "stopped"
        }
        
        for container in all_containers:
            name = container.name.lower()
            if "wallet-refresher" in name or "wallet_refresher" in name:
                services["wallet_refresher"] = container.status
            elif "executor" in name:
                services["executor"] = container.status
            elif "polyinsider-db" in name or "postgres" in name:
                services["db"] = container.status
        
        # Check DRY_RUN env
        dry_run = os.getenv("EXECUTOR_DRY_RUN", "true").lower() == "true"
        
        return {
            "wallet_refresher": services["wallet_refresher"],
            "executor": services["executor"],
            "db": services["db"],
            "dry_run": dry_run,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except docker.errors.DockerException:
        # Fallback if Docker not available
        return {
            "wallet_refresher": "unknown",
            "executor": "unknown",
            "db": "unknown",
            "dry_run": True,
            "timestamp": datetime.utcnow().isoformat(),
            "error": "Docker not accessible"
        }
