from __future__ import annotations

from typing import Any

from ..models.experiment import Experiment, metric_direction, metric_kind
from ..models.model_config import (
    MetricDefinition,
    ModelConfiguration,
    NormalizedMetric,
    ParameterDefinition,
)
from .experiment_store import ExperimentStore


class ModelService:
    def __init__(self, store: ExperimentStore):
        self.store = store

    def source(self) -> tuple[Experiment, dict[str, Any]]:
        experiment, raw, _ = self.store.load_source()
        self.store.ensure_model_buffer(raw)
        return experiment, raw

    def configuration(self) -> ModelConfiguration:
        experiment, _ = self.source()
        parameter_names = list(experiment.configuration)
        for name in experiment.critical_parameters:
            if name not in parameter_names:
                parameter_names.append(name)

        parameters: list[ParameterDefinition] = []
        for name in parameter_names:
            definition = dict(experiment.critical_parameters.get(name) or {})
            baseline = float(
                experiment.configuration.get(name, definition.get("baseline", 0.0))
            )
            ui_min = float(definition.get("min", baseline - max(abs(baseline) * 0.25, 0.01)))
            ui_max = float(definition.get("max", baseline + max(abs(baseline) * 0.25, 0.01)))
            if ui_min > ui_max:
                ui_min, ui_max = ui_max, ui_min
            sensitivity = definition.get("sensitivity") or {}
            parameters.append(
                ParameterDefinition(
                    name=name,
                    baseline=baseline,
                    ui_min=ui_min,
                    ui_max=ui_max,
                    valid_min=definition.get("valid_min"),
                    valid_max=definition.get("valid_max"),
                    critical=bool(definition.get("critical", False)),
                    sensitivity=sensitivity if isinstance(sensitivity, dict) else {},
                )
            )

        metrics = [
            MetricDefinition(
                name=metric.param,
                direction=metric_direction(metric.param),
                kind=metric_kind(metric.param),
                baseline_full=metric.full,
                baseline_compressed=metric.compressed,
            )
            for metric in experiment.metrics
        ]
        model_id = experiment.meta.model_id or "demo_model_v1"
        return ModelConfiguration(
            model_id=model_id,
            parameters=parameters,
            metrics=metrics,
            metadata={
                "full_model": experiment.meta.full_model,
                "compressed_model": experiment.meta.compressed_model,
                "experiment_id": experiment.experiment_id,
                "timestamp": experiment.meta.timestamp.isoformat(),
            },
        )

    def normalized_metrics(self) -> list[NormalizedMetric]:
        experiment, _ = self.source()
        normalized: list[NormalizedMetric] = []
        for metric in experiment.metrics:
            delta = metric.compressed - metric.full
            relative_delta = delta / metric.full if metric.full != 0 else None
            normalized.append(
                NormalizedMetric(
                    name=metric.param,
                    full=metric.full,
                    compressed=metric.compressed,
                    absolute_delta=delta,
                    relative_delta=relative_delta,
                    direction=metric_direction(metric.param),
                    kind=metric_kind(metric.param),
                )
            )
        return normalized

    def current_configuration(self) -> dict[str, float]:
        experiment, _ = self.source()
        buffer = self.store.load_buffer()
        candidate = buffer.get("configuration")
        if isinstance(candidate, dict):
            current: dict[str, float] = {}
            for name in experiment.configuration:
                if name in candidate and isinstance(candidate[name], (int, float)):
                    current[name] = float(candidate[name])
            if current and len(current) == len(experiment.configuration):
                return current
        return {name: float(value) for name, value in experiment.configuration.items()}

    def public_model(self) -> dict[str, Any]:
        config = self.configuration()
        current = self.current_configuration()
        normalized = self.normalized_metrics()
        return {
            "model_id": config.model_id,
            "parameters": [
                {
                    "name": parameter.name,
                    "baseline": parameter.baseline,
                    "ui_range": {"min": parameter.ui_min, "max": parameter.ui_max},
                    "valid_range": {
                        "min": parameter.valid_min,
                        "max": parameter.valid_max,
                    },
                    "critical": parameter.critical,
                    "sensitivity": parameter.sensitivity,
                }
                for parameter in config.parameters
            ],
            "current_configuration": current,
            "baseline": {
                "configuration": {
                    parameter.name: parameter.baseline for parameter in config.parameters
                },
                "metrics": {
                    metric.name: metric.baseline_compressed for metric in config.metrics
                },
            },
            "metrics": [
                {
                    **metric.as_dict(),
                    "definition": {
                        "direction": metric.direction,
                        "kind": metric.kind,
                    },
                }
                for metric in normalized
            ],
            "metadata": config.metadata,
            "constraints": {
                "quality_metrics": "[0, 1]",
                "latency_metrics": ">= 0",
                "memory_metrics": ">= 0",
                "unknown_parameters": "rejected",
                "missing_parameters": "rejected",
            },
        }