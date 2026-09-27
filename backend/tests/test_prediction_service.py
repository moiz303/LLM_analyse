from __future__ import annotations

import json
import math
from pathlib import Path

from ..app.config import Settings
from ..app.models.experiment import Experiment, normalize_experiment_payload
from ..app.services.preprocess_service import (
    convert_black_box_experiment,
    is_black_box_payload,
    preprocess_raw_payload,
)
from ..app.services.experiment_store import ExperimentStore


def black_box_document() -> dict:
    """A raw black box run following schemas/black_box_experiments_schema.json."""
    return {
        "schema_version": "1.0",
        "generated_at": "2026-09-15T10:05:00Z",
        "source_dataset": "wikitext",
        "experiments": [
            {
                "experiment_id": "exp_20260915_001",
                "timestamp": "2026-09-14T09:00:00Z",
                "timestamp_semantics": "run_finished_at",
                "full_model_identifier": {"model_id": "gemma-7b-fp16"},
                "compressed_model_identifier": {"variant": "gemma-nf4"},
                "configuration": {
                    "seed": 7,
                    "quantization_method": "nf4",
                    "target_bytes": 4_200_000_000,
                    "search_rounds": 3,
                    "minimum_nll_gain": 0.01,
                },
                "critical_parameters": {
                    "seed": {"critical": False, "type": "integer", "value": 7},
                    "quantization_method": {
                        "critical": True,
                        "type": "string",
                        "value": "nf4",
                    },
                    "target_bytes": {
                        "critical": True,
                        "type": "integer",
                        "value": 4_200_000_000,
                        "sensitivity": {"latency_ms": 0.02},
                    },
                    "search_rounds": {"critical": True, "type": "integer", "value": 3},
                    "minimum_nll_gain": {"critical": False, "type": "number", "value": 0.01},
                },
                "baseline_values": {
                    "seed": 7,
                    "quantization_method": "nf4",
                    "target_bytes": 4_200_000_000,
                    "search_rounds": 3,
                    "minimum_nll_gain": 0.01,
                },
                "parameter_ranges": {
                    "target_bytes": {"min": None, "max": 4_500_000_000},
                    "search_rounds": {"min": 1, "max": None},
                    "minimum_nll_gain": {"min": 0.001, "max": None},
                },
                "metrics": [
                    {
                        "param": "file_size_bytes",
                        "full": 14_000_000_000,
                        "compressed": 4_200_000_000,
                        "direction": "lower_is_better",
                        "unit": "bytes",
                    },
                    {
                        "param": "load_time_ms",
                        "full": 3200.5,
                        "compressed": 1150.25,
                        "direction": "lower_is_better",
                        "unit": "ms",
                    },
                    {
                        "param": "perplexity_wikitext",
                        "full": None,
                        "compressed": 8.42,
                        "direction": "lower_is_better",
                        "dataset": "wikitext",
                    },
                ],
                "per_class": [{"class": "class_1", "full": 0.81, "compressed": 0.79}],
                "parameter_analysis": {"ranking_available": True},
                "restoration": {"llama_tag": "b4000"},
            },
            {
                # Older run that must NOT be picked as the source of truth.
                "experiment_id": "exp_20260913_000",
                "timestamp": "2026-09-13T08:00:00Z",
                "full_model_identifier": {"model_id": "gemma-7b-fp16"},
                "compressed_model_identifier": {"variant": "gemma-q8"},
                "configuration": {},
                "critical_parameters": {},
                "baseline_values": {},
                "parameter_ranges": {},
                "metrics": [],
                "per_class": [],
            },
        ],
    }


COMPARISON_KEYS = {
    "experiment_id",
    "meta",
    "configuration",
    "critical_parameters",
    "metrics",
    "per_class",
}


def test_detects_black_box_and_legacy_shapes():
    assert is_black_box_payload(black_box_document())
    legacy = json.loads(Path(__file__).resolve().parents[2].joinpath("comparison.json").read_text())
    assert not is_black_box_payload(legacy)


def test_converts_latest_run_to_comparison_shape():
    converted = preprocess_raw_payload(black_box_document())

    assert set(converted) >= COMPARISON_KEYS
    assert converted["experiment_id"] == "exp_20260915_001"
    assert converted["meta"]["full_model"] == "gemma-7b-fp16"
    assert converted["meta"]["compressed_model"] == "gemma-nf4"
    assert converted["meta"]["timestamp"] == "2026-09-14T09:00:00Z"
    assert converted["meta"]["model_id"] == "exp_20260915_001"

    # configuration keeps every parameter that has a numeric value (including
    # nested tensor_type_map entries); only non-numeric ones are skipped
    assert converted["configuration"] == {
        "seed": 7.0,
        "target_bytes": 4_200_000_000.0,
        "search_rounds": 3.0,
        "minimum_nll_gain": 0.01,
    }
    assert "quantization_method" not in converted["configuration"]  # string value

    param_a = converted["critical_parameters"]["target_bytes"]
    assert param_a["critical"] is True
    assert param_a["baseline"] == 4_200_000_000.0
    assert param_a["max"] == 4_500_000_000.0
    assert "min" not in param_a  # null range bound stays absent, backend derives UI range
    assert param_a["sensitivity"] == {"latency_ms": 0.02}

    # metrics keep entries whose baseline side is null (JSON null -> NaN);
    # only fully unmeasured rows and extra metadata fields are dropped
    assert [entry["param"] for entry in converted["metrics"]] == [
        "file_size_bytes",
        "load_time_ms",
        "perplexity_wikitext",
    ]
    assert converted["metrics"][0] == {
        "param": "file_size_bytes",
        "full": 14_000_000_000.0,
        "compressed": 4_200_000_000.0,
    }
    perplexity = converted["metrics"][2]
    assert math.isnan(perplexity["full"])
    assert perplexity["compressed"] == 8.42
    assert "direction" not in perplexity and "dataset" not in perplexity

    assert converted["per_class"] == [{"class": "class_1", "full": 0.81, "compressed": 0.79}]
    # original run preserved for traceability
    assert converted["source_experiment"]["experiment_id"] == "exp_20260915_001"


def test_converted_output_passes_backend_validation():
    converted = preprocess_raw_payload(black_box_document())
    experiment = Experiment.model_validate(
        normalize_experiment_payload(converted, "blackbox")
    )
    assert experiment.experiment_id == "exp_20260915_001"
    assert len(experiment.metrics) == 3
    assert math.isnan(experiment.metrics[2].full)
    assert experiment.configuration["seed"] == 7.0


def test_legacy_comparison_json_passes_through_unchanged():
    legacy = json.loads(
        Path(__file__).resolve().parents[2].joinpath("comparison.json").read_text()
    )
    assert preprocess_raw_payload(legacy) == legacy


def test_preprocessing_is_idempotent():
    converted = preprocess_raw_payload(black_box_document())
    again = preprocess_raw_payload(converted)
    assert again["experiment_id"] == converted["experiment_id"]
    assert again["metrics"] == converted["metrics"]
    assert again["configuration"] == converted["configuration"]


def test_convert_single_experiment_object():
    single = black_box_document()["experiments"][0]
    converted = convert_black_box_experiment(single)
    assert converted["experiment_id"] == "exp_20260915_001"


def test_store_loads_black_box_file_as_source_of_truth(tmp_path: Path):
    comparison_path = tmp_path / "comparison.json"
    comparison_path.write_text(
        json.dumps(black_box_document()), encoding="utf-8"
    )
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
    store = ExperimentStore(settings)
    experiment, raw, path = store.load_source()
    assert experiment.experiment_id == "exp_20260915_001"
    assert path == comparison_path
    # the buffer written from the preprocessed payload is in comparison shape
    assert set(raw) >= COMPARISON_KEYS
    store.ensure_model_buffer(raw)
    buffer = json.loads((tmp_path / "data" / "model.json").read_text())
    assert "experiments" not in buffer
    assert buffer["meta"]["compressed_model"] == "gemma-nf4"
