from __future__ import annotations

from datetime import datetime
from math import isfinite
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def metric_kind(name: str) -> str:
    lowered = name.lower()
    if any(
        token in lowered
        for token in ("accuracy", "acc", "f1", "precision", "recall", "auc", "roc", "quality")
    ):
        return "quality"
    if any(token in lowered for token in ("latency", "time", "duration")):
        return "latency"
    if any(token in lowered for token in ("memory", "ram", "vram")):
        return "memory"
    return "generic"


def metric_direction(name: str) -> str:
    return "higher_is_better" if metric_kind(name) in {"quality", "generic"} else "lower_is_better"


class ExperimentMeta(BaseModel):
    model_config = ConfigDict(extra="ignore")

    full_model: str = Field(min_length=1)
    compressed_model: str = Field(min_length=1)
    timestamp: datetime
    model_id: str | None = Field(default=None, min_length=1)


class MetricResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    param: str = Field(min_length=1)
    full: float
    compressed: float

    @field_validator("full", "compressed")
    @classmethod
    def finite_value(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("metric values must be finite numbers")
        return value

    @model_validator(mode="after")
    def validate_metric_range(self) -> "MetricResult":
        kind = metric_kind(self.param)
        values = (self.full, self.compressed)
        if kind == "quality" and any(value < 0 or value > 1 for value in values):
            raise ValueError(f"quality metric '{self.param}' must be in [0, 1]")
        if kind in {"latency", "memory"} and any(value < 0 for value in values):
            raise ValueError(f"{kind} metric '{self.param}' must be non-negative")
        return self


class PerClassMetric(BaseModel):
    model_config = ConfigDict(extra="ignore")

    class_name: str = Field(alias="class", min_length=1)
    full: float = Field(ge=0, le=1)
    compressed: float = Field(ge=0, le=1)

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class Experiment(BaseModel):
    model_config = ConfigDict(extra="ignore")

    experiment_id: str = Field(min_length=1)
    meta: ExperimentMeta
    configuration: dict[str, float] = Field(default_factory=dict)
    critical_parameters: dict[str, dict[str, Any]] = Field(default_factory=dict)
    metrics: list[MetricResult] = Field(min_length=1)
    per_class: list[PerClassMetric] = Field(default_factory=list)

    @field_validator("configuration")
    @classmethod
    def finite_configuration(cls, value: dict[str, float]) -> dict[str, float]:
        if not value:
            return value
        for name, parameter in value.items():
            if not name.strip():
                raise ValueError("configuration parameter names cannot be empty")
            if not isfinite(parameter):
                raise ValueError(f"configuration value for '{name}' must be finite")
        return value

    @model_validator(mode="after")
    def fill_critical_baselines(self) -> "Experiment":
        for name, definition in self.critical_parameters.items():
            if name in self.configuration and "baseline" not in definition:
                definition["baseline"] = self.configuration[name]
        return self


def normalize_experiment_payload(payload: dict[str, Any], fallback_id: str = "comparison_baseline") -> dict[str, Any]:
    """Accept the legacy comparison.json shape and normalize it to one contract."""
    normalized = dict(payload)
    normalized.setdefault("experiment_id", fallback_id)
    normalized.setdefault("critical_parameters", {})
    normalized.setdefault("configuration", {})
    normalized.setdefault("per_class", [])
    meta = dict(normalized.get("meta") or {})
    normalized["meta"] = meta

    # Older comparison files contain only full/compressed model names and metrics.
    # The timestamp remains mandatory because it is also the actual datapoint time.
    if not meta.get("model_id"):
        meta["model_id"] = payload.get("model_id") or "demo_model_v1"

    for name, definition in normalized["critical_parameters"].items():
        if name not in normalized["configuration"] and "baseline" in definition:
            normalized["configuration"][name] = definition["baseline"]
    return normalized