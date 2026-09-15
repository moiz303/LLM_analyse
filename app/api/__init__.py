"""
API __init__.
"""
from app.api.model import router as model_router
from app.api.predict import router as predict_router
from app.api.health import router as health_router

__all__ = ["model_router", "predict_router", "health_router"]
