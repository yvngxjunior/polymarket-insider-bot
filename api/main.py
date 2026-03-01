from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from api.routes import health, dashboard, portfolio, positions, trades, wallets, monitoring
from api.database import engine, Base

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="PolyInsider API",
    description="Professional Polymarket Copy Trading Bot API",
    version="3.2.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router)
app.include_router(dashboard.router)
app.include_router(portfolio.router)
app.include_router(positions.router)
app.include_router(trades.router)
app.include_router(wallets.router)
app.include_router(monitoring.router)  # NEW

@app.get("/")
async def root():
    return {
        "app": "PolyInsider Bot",
        "version": "3.2.0",
        "docs": "/docs",
        "health": "/health"
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
