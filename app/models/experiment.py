"""
Pydantic models for experiment JSON validation.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class MetricConfig(BaseModel):
    """Configuration for a single metric."""
    direction: str = Field(..., description="higher_is_better or lower_is_better")


class ParameterSensitivity(BaseModel):
    """Sensitivity information for a parameter."""
    accuracy_top1: Optional[float] = None
    f1_macro: Optional[float] = None
    latency_ms: Optional[float] = None
    memory_mb: Optional[float] = None


class ParameterConfig(BaseModel):
    """Configuration for a single parameter."""
    baseline: float = Field(..., ge=0)
    ui_min: float = Field(..., ge=0)
    ui_max: float = Field(..., ge=0)
    sensitivity: Optional[Dict[str, float]] = None
    
    @field_validator('ui_max')
    @classmethod
    def check_ui_range(cls, v: float, info) -> float:
        values = info.data
        if 'ui_min' in values and v < values['ui_min']:
            raise ValueError('ui_max must be >= ui_min')
        return v


class ModelConfiguration(BaseModel):
    """Model configuration with parameters and metrics definitions."""
    model_id: str = Field(..., description="Unique model identifier")
    parameters: Dict[str, ParameterConfig] = Field(..., description="Parameter configurations")
    metrics: Dict[str, MetricConfig] = Field(..., description="Metric definitions")


class CriticalParameterInfo(BaseModel):
    """Critical parameter information from black box."""
    critical: bool
    baseline: float
    min: float
    max: float


class MetricData(BaseModel):
    """Single metric data point."""
    param: str
    full: float = Field(..., ge=0)
    compressed: float = Field(..., ge=0)
    
    @field_validator('full', 'compressed')
    @classmethod
    def check_accuracy_range(cls, v: float, info) -> float:
        # For accuracy/f1 metrics, validate [0, 1] range
        param = info.data.get('param', '')
        if param in ['accuracy_top1', 'accuracy_top5', 'f1_macro']:
            if not (0 <= v <= 1):
                raise ValueError(f'{param} must be in range [0, 1]')
        return v


class PerClassMetric(BaseModel):
    """Per-class metric data."""
    class_name: str = Field(..., alias='class')
    full: float = Field(..., ge=0, le=1)
    compressed: float = Field(..., ge=0, le=1)


class ExperimentMeta(BaseModel):
    """Experiment metadata."""
    full_model: str
    compressed_model: str
    timestamp: datetime


class ExperimentJSON(BaseModel):
    """Main experiment JSON schema from black box."""
    experiment_id: str = Field(..., description="Unique experiment identifier")
    meta: ExperimentMeta
    configuration: Dict[str, float] = Field(..., description="Parameter values")
    critical_parameters: Optional[Dict[str, CriticalParameterInfo]] = None
    metrics: List[MetricData]
    per_class: List[PerClassMetric] = Field(default_factory=list)
    
    class Config:
        populate_by_name = True
