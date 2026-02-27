"""FastAPI application entry point.

Usage:
    Local dev:  uvicorn api.main:app --reload --port 8000
    Heroku:     web: uvicorn api.main:app --host 0.0.0.0 --port $PORT
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from bot.database import init_db
from bot.utils.logger import logger

from api.routes import positions, portfolio, trades, wallets, health, dashboard


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB. Shutdown: cleanup."""
    logger.info("[API] Initializing database...")
    init_db()
    logger.info("[API] FastAPI started. Docs: /docs")
    yield
    logger.info("[API] FastAPI shutdown.")


app = FastAPI(
    title="PolyInsider Bot API",
    description="REST API for Polymarket copy trading bot - positions, trades, portfolio analytics",
    version="3.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware (allow frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict to frontend domain in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"[API] Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)},
    )

# Register routes
app.include_router(health.router, tags=["Health"])
app.include_router(dashboard.router, prefix="/api", tags=["Dashboard"])
app.include_router(positions.router, prefix="/api", tags=["Positions"])
app.include_router(portfolio.router, prefix="/api", tags=["Portfolio"])
app.include_router(trades.router, prefix="/api", tags=["Trades"])
app.include_router(wallets.router, prefix="/api", tags=["Wallets"])


@app.get("/", tags=["Root"])
async def root():
    return {
        "service": "PolyInsider Bot API",
        "version": "3.1.0",
        "docs": "/docs",
        "health": "/health",
    }
