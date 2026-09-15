from typing import Dict, Any, Optional
from pydantic import BaseModel


class PredictionResult(BaseModel):
    """Result of a prediction."""
    prediction: Dict[str, float]
    baseline: Dict[str, float]
    support_score: float
    support_level: str  # "high", "medium", "low"
    prediction_mode: str
