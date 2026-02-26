"""Health check endpoint."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint for uptime monitoring.
    
    Returns:
        Status OK if service is running.
    """
    return {"status": "ok", "service": "polyinsider-api", "version": "3.1.0"}
