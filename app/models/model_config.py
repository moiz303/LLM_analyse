"""
Model configuration and prediction models.
"""
from typing import Dict, Optional
from pydantic import BaseModel, Field


class ParameterConfig(BaseModel):
    """Configuration for a single parameter."""
    baseline: float
    ui_min: float
    ui_max: float
    sensitivity: Optional[Dict[str, float]] = None


class MetricConfig(BaseModel):
    """Configuration for a metric."""
    direction: str  # "higher_is_better" or "lower_is_better"


class ModelConfiguration(BaseModel):
    """Full model configuration."""
    model_id: str
    parameters: Dict[str, ParameterConfig]
    metrics: Dict[str, MetricConfig]


class PredictionRequest(BaseModel):
    """Request for prediction endpoint."""
    parameters: Dict[str, float]


class NormalizedMetric(BaseModel):
    """Normalized metric with delta calculations."""
    name: str
    full: float
    compressed: float
    absolute_delta: float
    relative_delta: float
    direction: str


class PredictionResponse(BaseModel):
    """Response from prediction endpoint."""
    prediction_mode: str
    prediction: Dict[str, float]
    baseline: Dict[str, float]
    support: Dict[str, any] = {}  # Placeholder for flexible support data
