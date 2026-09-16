from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.experiment import Experiment


def valid_payload() -> dict:
    return {
        "experiment_id": "exp_001",
        "meta": {
            "full_model": "full",
            "compressed_model": "compressed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "configuration": {"param_a": 0.8},
        "metrics": [
            {"param": "accuracy_top1", "full": 0.8, "compressed": 0.7},
        ],
        "per_class": [],
    }


def test_valid_experiment_is_accepted():
    experiment = Experiment.model_validate(valid_payload())
    assert experiment.experiment_id == "exp_001"


def test_invalid_quality_metric_is_rejected():
    payload = valid_payload()
    payload["metrics"][0]["compressed"] = 1.2
    with pytest.raises(ValidationError):
        Experiment.model_validate(payload)


def test_missing_required_meta_is_rejected():
    payload = valid_payload()
    del payload["meta"]["timestamp"]
    with pytest.raises(ValidationError):
        Experiment.model_validate(payload)