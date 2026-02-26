"""Run FastAPI backend with hot reload.

This script must be run from the bot root directory:
    cd polymarket-insider-bot
    python backend/run.py

Or from backend/ directory:
    cd backend
    python run.py
"""

import sys
import os
from pathlib import Path
import uvicorn

# Ensure we're running from bot root
script_dir = Path(__file__).resolve().parent
bot_root = script_dir.parent

# Change to bot root if we're in backend/
if os.getcwd().endswith('backend'):
    os.chdir(bot_root)
    print(f"Changed working directory to: {bot_root}")

# Add bot root to Python path
if str(bot_root) not in sys.path:
    sys.path.insert(0, str(bot_root))

if __name__ == "__main__":
    print(f"Starting API from: {os.getcwd()}")
    print(f"Python path includes: {bot_root}")
    
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=[str(bot_root / "backend")],
        log_level="info",
    )
