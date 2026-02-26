"FastAPI backend for PolyInsider Bot dashboard."

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import sys

# Add bot root to path to import bot modules
bot_root = Path(__file__).parent.parent
sys.path.insert(0, str(bot_root))

from backend.app.routers import settings

app = FastAPI(
    title="PolyInsider Bot API",
    description="Dashboard API for Polymarket copy trading bot",
    version="2.0.0",
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.js dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(settings.router)


@app.get("/")
async def root():
    return {
        "message": "PolyInsider Bot API v2.0",
        "status": "online",
        "endpoints": [
            "/api/settings (GET, PUT)",
            "/api/portfolio (GET)",
            "/api/trades (GET)",
            "/api/metrics (GET)",
        ],
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
