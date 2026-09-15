"""
API endpoints for model configuration.
"""
from fastapi import APIRouter, HTTPException

from app.models.model_config import ModelConfiguration

router = APIRouter(prefix="/api/model", tags=["model"])


@router.get("", response_model=ModelConfiguration)
async def get_model():
    """
    Get the current model configuration.
    
    Returns:
        Model configuration including:
        - model_id
        - parameters with baseline, ui_min, ui_max
        - metrics with direction
    """
    from app.main import get_app_services
    
    services = get_app_services()
    if services is None:
        raise HTTPException(status_code=503, detail="Services not initialized")
    
    model_config = services["model_service"].get_model_configuration()
    
    if model_config is None:
        raise HTTPException(status_code=404, detail="No model configuration available")
    
    return model_config
