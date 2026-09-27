from __future__ import annotations
from copy import deepcopy
from typing import Any


class ComparisonPreprocessError(ValueError):
    """Raised when the source payload cannot be converted unambiguously."""


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ComparisonPreprocessError(f"{path} must be an object")
    return value


def _require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ComparisonPreprocessError(f"{path} must be an array")
    return value


def _first_not_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _source_experiment(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Accept both:
      1. canonical black-box export: {experiments: [...]}
      2. a single experiment object: {...}
    """
    if isinstance(payload.get("experiments"), list):
        experiments = payload["experiments"]
        if not experiments:
            raise ComparisonPreprocessError("experiments must contain at least one experiment")
        if len(experiments) != 1:
            raise ComparisonPreprocessError(
                "Expected exactly one experiment; pass one experiment at a time"
            )
        return _require_mapping(experiments[0], "experiments[0]")

    return payload


def _model_meta(exp: dict[str, Any]) -> dict[str, Any]:
    full = exp.get("full_model_identifier") or {}
    compressed = exp.get("compressed_model_identifier") or {}

    full = _require_mapping(full, "full_model_identifier")
    compressed = _require_mapping(compressed, "compressed_model_identifier")

    full_model = _first_not_none(
        full.get("model_id"),
        full.get("artifact"),
    )
    compressed_model = _first_not_none(
        compressed.get("variant"),
        compressed.get("model_id"),
        compressed.get("artifact"),
    )

    model_id = _first_not_none(
        exp.get("model_id"),
        full.get("model_id"),
        exp.get("configuration", {}).get("source_model_id")
        if isinstance(exp.get("configuration"), dict)
        else None,
        exp.get("experiment_id"),
    )

    return {
        "full_model": full_model,
        "compressed_model": compressed_model,
        "timestamp": exp.get("timestamp"),
        "model_id": model_id,
    }


def _parameter_names(exp: dict[str, Any]) -> list[str]:
    ranges = exp.get("parameter_ranges")
    if not isinstance(ranges, dict):
        configuration = _require_mapping(exp.get("configuration", {}), "configuration")
        excluded = {
            "source_model_id",
            "source_revision",
            "seed",
            "llama_tag",
            "llama_commit",
            "calibration_version",
            "quantization_method",
            "token_embedding_type",
            "output_tensor_type",
            "tensor_map_artifact",
            "tensor_type_map",
            "imatrix_artifact",
            "imatrix_sha256",
        }
        names = [name for name in configuration if name not in excluded]
        if not names:
            raise ComparisonPreprocessError(
                "Could not discover configurable parameters"
            )
        return names

    names = [name for name in ranges.keys()]
    if not names:
        raise ComparisonPreprocessError("parameter_ranges is empty")
    return names


def _configuration(exp: dict[str, Any], parameter_names: list[str]) -> dict[str, Any]:
    source_config = _require_mapping(exp.get("configuration", {}), "configuration")
    result: dict[str, Any] = {}

    for name in parameter_names:
        if name in source_config:
            result[name] = source_config[name]
            continue

        # Some exporters expose the selected value only in baseline_values.
        baseline = exp.get("baseline_values")
        if isinstance(baseline, dict) and name in baseline:
            result[name] = baseline[name]
            continue

        critical = exp.get("critical_parameters")
        if isinstance(critical, dict):
            entry = critical.get(name)
            if isinstance(entry, dict) and "value" in entry:
                result[name] = entry["value"]

    return result


def _critical_parameters(exp: dict[str, Any], parameter_names: list[str], metric_names: list[str]) -> dict[str, Any]:
    ranges = exp.get("parameter_ranges")
    ranges = ranges if isinstance(ranges, dict) else {}

    critical_source = exp.get("critical_parameters")
    critical_source = critical_source if isinstance(critical_source, dict) else {}

    baseline_source = exp.get("baseline_values")
    baseline_source = baseline_source if isinstance(baseline_source, dict) else {}

    result: dict[str, Any] = {}

    for name in parameter_names:
        source_critical = critical_source.get(name)
        source_critical = (
            source_critical if isinstance(source_critical, dict) else {}
        )

        range_value = ranges.get(name)
        range_value = range_value if isinstance(range_value, dict) else {}

        baseline = _first_not_none(
            baseline_source.get(name),
            source_critical.get("value"),
            exp.get("configuration", {}).get(name)
            if isinstance(exp.get("configuration"), dict)
            else None,
        )

        item: dict[str, Any] = {
            "critical": bool(source_critical.get("critical", True)),
            "baseline": baseline,
            "min": range_value.get("min"),
            "max": range_value.get("max"),
        }

        sensitivity = _find_sensitivity(exp, name, metric_names)
        if sensitivity:
            item["sensitivity"] = sensitivity

        result[name] = item

    return result


def _find_sensitivity(exp: dict[str, Any], parameter_name: str, metric_names: list[str]) -> dict[str, Any]:
    """
    Best-effort structural lookup for exporters that already contain sensitivity.

    Supported locations:
      critical_parameters.<param>.sensitivity
      parameter_sensitivity.<param>
      sensitivity.<param>
    """
    critical = exp.get("critical_parameters")
    if isinstance(critical, dict):
        entry = critical.get(parameter_name)
        if isinstance(entry, dict) and isinstance(entry.get("sensitivity"), dict):
            return deepcopy(entry["sensitivity"])

    for container_name in ("parameter_sensitivity", "sensitivity"):
        container = exp.get(container_name)
        if isinstance(container, dict):
            entry = container.get(parameter_name)
            if isinstance(entry, dict):
                return deepcopy(entry)

    return {}


def _metrics(exp: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    source = _require_list(exp.get("metrics", []), "metrics")
    result: list[dict[str, Any]] = []
    names: list[str] = []

    for index, item in enumerate(source):
        item = _require_mapping(item, f"metrics[{index}]")
        param = item.get("param")

        if not isinstance(param, str) or not param:
            raise ComparisonPreprocessError(
                f"metrics[{index}].param must be a non-empty string"
            )

        metric = {
            "param": param,
            "full": item.get("full"),
            "compressed": item.get("compressed"),
        }

        for key in ("direction", "unit", "dataset"):
            if key in item:
                metric[key] = item[key]

        result.append(metric)
        names.append(param)

    return result, names


def preprocess_comparison(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Convert one black-box export into the compact comparison object
    """
    payload = _require_mapping(payload, "payload")

    if (
        isinstance(payload.get("meta"), dict)
        and isinstance(payload.get("configuration"), dict)
        and isinstance(payload.get("critical_parameters"), dict)
        and isinstance(payload.get("metrics"), list)
        and "experiment_id" in payload
        and "experiments" not in payload
    ):
        return deepcopy(payload)

    exp = _source_experiment(payload)

    experiment_id = exp.get("experiment_id")
    if not isinstance(experiment_id, str) or not experiment_id:
        raise ComparisonPreprocessError(
            "experiment_id must be a non-empty string"
        )

    parameter_names = _parameter_names(exp)
    metrics, metric_names = _metrics(exp)

    configuration = _configuration(exp, parameter_names)
    critical_parameters = _critical_parameters(
        exp, parameter_names, metric_names
    )

    result: dict[str, Any] = {
        "experiment_id": experiment_id,
        "meta": _model_meta(exp),
        "configuration": configuration,
        "critical_parameters": critical_parameters,
        "metrics": metrics,
        "per_class": deepcopy(exp.get("per_class", [])),
    }

    return result


def preprocess_json_file(source_path: str, destination_path: str) -> None:
    import json
    from pathlib import Path

    source = Path(source_path)
    destination = Path(destination_path)

    with source.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    normalized = preprocess_comparison(payload)

    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        json.dump(normalized, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


__all__ = [
    "ComparisonPreprocessError",
    "preprocess_comparison",
    "preprocess_json_file",
]
