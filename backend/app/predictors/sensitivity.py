from __future__ import annotations

from math import sqrt
from typing import Any

from ..models.experiment import Experiment
from ..models.model_config import ModelConfiguration, ParameterDefinition
from .base import Predictor


class PredictionInputError(ValueError):
    pass


class SensitivityPredictor(Predictor):
    mode = "sensitivity_model"

    def __init__(
        self,
        model: ModelConfiguration,
        source_experiment: Experiment,
        experiments: list[Experiment],
    ):
        self.model = model
        self.source_experiment = source_experiment
        self.experiments = experiments

    def validate_configuration(self, configuration: dict[str, float]) -> None:
        expected = set(self.model.parameter_map)
        received = set(configuration)
        unknown = sorted(received - expected)
        missing = sorted(expected - received)
        if unknown:
            raise PredictionInputError(f"unknown parameters: {', '.join(unknown)}")
        if missing:
            raise PredictionInputError(f"missing parameters: {', '.join(missing)}")
        for name, value in configuration.items():
            parameter = self.model.parameter_map[name]
            if not isinstance(value, (int, float)):
                raise PredictionInputError(f"parameter '{name}' must be numeric")
            if parameter.valid_min is not None and value < parameter.valid_min:
                raise PredictionInputError(
                    f"parameter '{name}' is below valid minimum {parameter.valid_min}"
                )
            if parameter.valid_max is not None and value > parameter.valid_max:
                raise PredictionInputError(
                    f"parameter '{name}' is above valid maximum {parameter.valid_max}"
                )
            if value < parameter.ui_min or value > parameter.ui_max:
                raise PredictionInputError(
                    f"parameter '{name}' must be in UI range "
                    f"[{parameter.ui_min}, {parameter.ui_max}]"
                )

    @staticmethod
    def _sensitivity_for(
        parameter: ParameterDefinition, metric_name: str, kind: str
    ) -> tuple[float, float, float, float]:
        raw: Any = parameter.sensitivity.get(metric_name)
        if raw is None:
            raw = parameter.sensitivity.get(kind)
        if isinstance(raw, (int, float)):
            return float(raw), float(raw), 1.0, 1.0
        if isinstance(raw, dict):
            default = float(raw.get("alpha", raw.get("value", 0.0)))
            lower = float(raw.get("lower", raw.get("alpha_lower", default)))
            upper = float(raw.get("upper", raw.get("alpha_upper", default)))
            power_lower = float(raw.get("power_lower", raw.get("power", 1.0)))
            power_upper = float(raw.get("power_upper", raw.get("power", 1.0)))
            return lower, upper, power_lower, power_upper

        # These defaults are intentionally modest: the predictor is an
        # explainable fallback, not a claim of statistical certainty.
        if kind == "quality":
            return (0.06 if parameter.critical else 0.03,) * 2 + (1.0, 1.0)
        if kind in {"latency", "memory"}:
            return (0.12 if parameter.critical else 0.06,) * 2 + (1.0, 1.0)
        return (0.05,) * 2 + (1.0, 1.0)

    def _normalized_deviation(
        self, parameter: ParameterDefinition, value: float
    ) -> float:
        if value == parameter.baseline:
            return 0.0
        if value < parameter.baseline:
            denominator = parameter.baseline - parameter.ui_min
        else:
            denominator = parameter.ui_max - parameter.baseline
        return (value - parameter.baseline) / denominator if denominator else 0.0

    def _penalty(self, metric_name: str, kind: str, configuration: dict[str, float]) -> float:
        total = 0.0
        for parameter in self.model.parameters:
            deviation = self._normalized_deviation(parameter, configuration[parameter.name])
            lower, upper, power_lower, power_upper = self._sensitivity_for(
                parameter, metric_name, kind
            )
            if deviation < 0:
                total += lower * abs(deviation) ** power_lower
            else:
                total += upper * abs(deviation) ** power_upper
        return total

    def predict(self, configuration: dict[str, float]) -> dict[str, float]:
        self.validate_configuration(configuration)
        prediction: dict[str, float] = {}
        for metric in self.model.metrics:
            penalty = self._penalty(metric.name, metric.kind, configuration)
            if metric.kind == "quality":
                value = metric.baseline_compressed - penalty
                value = max(0.0, min(1.0, value))
            elif metric.kind in {"latency", "memory"}:
                value = max(0.0, metric.baseline_compressed * (1.0 + penalty))
            else:
                if metric.direction == "higher_is_better":
                    value = max(0.0, metric.baseline_compressed - penalty)
                else:
                    value = max(0.0, metric.baseline_compressed * (1.0 + penalty))
            prediction[metric.name] = float(value)
        return prediction

    def support(self, configuration: dict[str, float]) -> dict[str, Any]:
        known = [self.source_experiment, *self.experiments]
        if not known:
            return {
                "score": 0.0,
                "level": "low",
                "nearest_experiment_id": None,
                "distance": 0.0,
            }

        distances: list[tuple[float, str]] = []
        for experiment in known:
            values = []
            for parameter in self.model.parameters:
                baseline = parameter.baseline
                span = max(parameter.ui_max - parameter.ui_min, 1e-9)
                candidate = experiment.configuration.get(parameter.name, baseline)
                values.append((configuration[parameter.name] - candidate) / span)
            distance = sqrt(sum(value * value for value in values) / max(len(values), 1))
            distances.append((distance, experiment.experiment_id))

        nearest_distance, nearest_id = min(distances, key=lambda item: item[0])
        score = max(0.0, min(1.0, 1.0 - nearest_distance))
        level = "high" if score >= 0.8 else "medium" if score >= 0.5 else "low"
        return {
            "score": score,
            "level": level,
            "nearest_experiment_id": nearest_id,
            "distance": nearest_distance,
        }