"""
Health check endpoint.
"""
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """
    Health check endpoint.
    
    Returns:
        {"status": "ok"} if the service is healthy
    """
    return {"status": "ok"}
