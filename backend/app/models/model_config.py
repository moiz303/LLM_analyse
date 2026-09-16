from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SensitivityDefinition(BaseModel):
    model_config = ConfigDict(extra="allow")

    lower: float | None = Field(default=None, ge=0)
    upper: float | None = Field(default=None, ge=0)
    power_lower: float = Field(default=1.0, gt=0)
    power_upper: float = Field(default=1.0, gt=0)


class ParameterDefinition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    baseline: float
    ui_min: float
    ui_max: float
    valid_min: float | None = None
    valid_max: float | None = None
    critical: bool = False
    sensitivity: dict[str, Any] = Field(default_factory=dict)


class MetricDefinition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    direction: str
    kind: str
    baseline_full: float
    baseline_compressed: float


class ModelConfiguration(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model_id: str
    parameters: list[ParameterDefinition]
    metrics: list[MetricDefinition]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def parameter_map(self) -> dict[str, ParameterDefinition]:
        return {parameter.name: parameter for parameter in self.parameters}

    @property
    def metric_map(self) -> dict[str, MetricDefinition]:
        return {metric.name: metric for metric in self.metrics}


@dataclass(frozen=True)
class NormalizedMetric:
    name: str
    full: float
    compressed: float
    absolute_delta: float
    relative_delta: float | None
    direction: str
    kind: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "full": self.full,
            "compressed": self.compressed,
            "absolute_delta": self.absolute_delta,
            "relative_delta": self.relative_delta,
            "direction": self.direction,
            "kind": self.kind,
        }