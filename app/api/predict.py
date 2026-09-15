"""
API endpoints for predictions.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException

from app.models.model_config import PredictionRequest
from app.models.prediction import PredictionResult

router = APIRouter(prefix="/api/predict", tags=["prediction"])


@router.post("", response_model=PredictionResult)
async def predict(request: PredictionRequest):
    """
    Make a prediction for the given parameter configuration.
    
    Request body:
        parameters: Dictionary of parameter values
    
    Returns:
        Prediction result including:
        - prediction: predicted metric values
        - baseline: baseline metric values
        - support_score: confidence score (0-1)
        - support_level: "high", "medium", or "low"
        - prediction_mode: type of predictor used
    """
    from app.main import get_app_services
    
    services = get_app_services()
    if services is None:
        raise HTTPException(status_code=503, detail="Services not initialized")
    
    prediction_service = services["prediction_service"]
    influx_service = services["influx_service"]
    model_service = services["model_service"]
    
    # Validate configuration
    is_valid, error_msg = prediction_service.validate_configuration(request.parameters)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)
    
    # Make prediction
    result = prediction_service.predict(request.parameters)
    
    # Write prediction to InfluxDB
    model_config = model_service.get_model_configuration()
    if model_config:
        try:
            influx_service.write_prediction(
                model_id=model_config.model_id,
                configuration=request.parameters,
                predictions=result.prediction,
                support_score=result.support_score,
                support_level=result.support_level,
                prediction_mode=result.prediction_mode,
                timestamp=datetime.now(timezone.utc)
            )
        except Exception as e:
            # Log error but don't fail the request
            print(f"Warning: Could not write prediction to InfluxDB: {e}")
    
    return result
