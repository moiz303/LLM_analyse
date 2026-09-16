from app.models.experiment import Experiment
from app.models.model_config import (
    MetricDefinition,
    ModelConfiguration,
    ParameterDefinition,
)
from app.predictors.sensitivity import SensitivityPredictor


def build_predictor() -> SensitivityPredictor:
    source = Experiment.model_validate(
        {
            "experiment_id": "baseline",
            "meta": {
                "full_model": "full",
                "compressed_model": "compressed",
                "timestamp": "2026-01-01T00:00:00Z",
            },
            "configuration": {"param_a": 0.5},
            "metrics": [
                {"param": "accuracy_top1", "full": 0.8, "compressed": 0.75},
                {"param": "latency_ms", "full": 20, "compressed": 10},
            ],
        }
    )
    model = ModelConfiguration(
        model_id="model",
        parameters=[
            ParameterDefinition(
                name="param_a",
                baseline=0.5,
                ui_min=0.0,
                ui_max=1.0,
                sensitivity={"accuracy_top1": 0.1},
            )
        ],
        metrics=[
            MetricDefinition(
                name="accuracy_top1",
                direction="higher_is_better",
                kind="quality",
                baseline_full=0.8,
                baseline_compressed=0.75,
            ),
            MetricDefinition(
                name="latency_ms",
                direction="lower_is_better",
                kind="latency",
                baseline_full=20,
                baseline_compressed=10,
            ),
        ],
    )
    return SensitivityPredictor(model, source, [])


def test_baseline_is_exactly_anchored():
    predictor = build_predictor()
    assert predictor.predict({"param_a": 0.5}) == {
        "accuracy_top1": 0.75,
        "latency_ms": 10.0,
    }


def test_parameter_change_changes_prediction():
    predictor = build_predictor()
    result = predictor.predict({"param_a": 1.0})
    assert result["accuracy_top1"] < 0.75
    assert result["latency_ms"] >= 10.0


def test_unknown_parameter_is_rejected():
    predictor = build_predictor()
    try:
        predictor.predict({"other": 0.5})
    except ValueError as exc:
        assert "unknown parameters" in str(exc)
    else:
        raise AssertionError("unknown parameter was accepted")