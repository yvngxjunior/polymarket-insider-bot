"""Run FastAPI backend with hot reload."""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",  # Import string format (required for reload)
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["backend"],  # Only watch backend directory
        log_level="info",
    )
