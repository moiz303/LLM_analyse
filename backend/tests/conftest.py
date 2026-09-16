from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import Settings
from app.main import create_app


@pytest.fixture
def test_app(tmp_path: Path):
    comparison = {
        "experiment_id": "exp_test",
        "meta": {
            "full_model": "full",
            "compressed_model": "compressed",
            "timestamp": "2026-01-01T00:00:00Z",
            "model_id": "test_model",
        },
        "configuration": {"param_a": 0.5, "param_b": 1.0},
        "critical_parameters": {
            "param_a": {
                "critical": True,
                "baseline": 0.5,
                "min": 0.0,
                "max": 1.0,
                "sensitivity": {"accuracy_top1": 0.1},
            },
            "param_b": {
                "critical": False,
                "baseline": 1.0,
                "min": 0.5,
                "max": 1.5,
            },
        },
        "metrics": [
            {"param": "accuracy_top1", "full": 0.8, "compressed": 0.75},
            {"param": "f1_macro", "full": 0.7, "compressed": 0.65},
            {"param": "latency_ms", "full": 20, "compressed": 10},
            {"param": "memory_mb", "full": 100, "compressed": 50},
        ],
        "per_class": [],
    }
    comparison_path = tmp_path / "comparison.json"
    comparison_path.write_text(json.dumps(comparison), encoding="utf-8")
    settings = Settings(
        data_dir=tmp_path / "data",
        comparison_path=comparison_path,
        model_path=tmp_path / "data" / "model.json",
        experiments_dir=tmp_path / "data" / "experiments",
        influx_url="",
        influx_org="",
        influx_bucket="",
        influx_token="",
        influx_required=False,
        cors_origins=["http://localhost:5173"],
    )
    return create_app(settings)