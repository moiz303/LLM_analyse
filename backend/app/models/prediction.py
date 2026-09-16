from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parameters: dict[str, float] = Field(min_length=1)


class SupportInfo(BaseModel):
    score: float = Field(ge=0, le=1)
    level: str
    nearest_experiment_id: str | None = None
    distance: float = Field(ge=0)


class PredictionResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prediction_mode: str
    model_id: str
    prediction: dict[str, float]
    baseline: dict[str, float]
    configuration: dict[str, float]
    support: SupportInfo
    metrics: list[dict[str, Any]] = Field(default_factory=list)
    persisted: bool = True