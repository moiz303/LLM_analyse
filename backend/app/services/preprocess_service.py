from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from .schema_utils import (
    collect_object_keys,
    experiment_schema_node,
    load_cached_schema,
    load_schema,
)

# Non-numeric tokens that occasionally appear instead of real numbers.
_SKIP_MARKERS = ("n/a", "na", "null", "none", "unknown")

# Schema property names that describe *how* a value is stored rather than the
# value itself; they must never be mistaken for tunable parameters.
_META_KEYS = frozenset({"critical", "type", "value", "min", "max", "sensitivity"})

# Only these leaf types can carry a scalar measurement; anything else
# (objects like tensor maps, arrays, booleans-as-flags) is metadata.
_SCALAR_TYPES = frozenset({"integer", "number"})

# A dotted key such as ``blk.12.attn_q.weight`` is flattened into a single
# parameter name; separators inside names are normalized to underscores.
_DOTTED_KEY_RE = re.compile(r"[^0-9A-Za-z._-]+")


# ---------------------------------------------------------------------------
# Numeric conversion helpers
# ---------------------------------------------------------------------------


def _as_float(value: Any) -> float | None:
    """Best-effort numeric conversion; returns None when the value is not a number."""
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", ".")
        if text.lower() in _SKIP_MARKERS:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _is_meaningful(value: Any) -> bool:
    """True when a harvested raw value actually carries information.

    ``None``, empty strings and placeholder tokens such as "N/A" mean "this
    section simply did not measure the parameter"; they must not be confused
    with genuine string values (``quantization_method="nf4"``) that we now
    keep instead of silently dropping them.
    """
    if value is None:
        return False
    if isinstance(value, str):
        text = value.strip()
        return bool(text) and text.lower() not in _SKIP_MARKERS
    if isinstance(value, float):
        return math.isfinite(value)
    return isinstance(value, (int, bool, str))


def _json_number(value: float | None) -> float | None:
    """Encode an unknown (None) numeric as NaN so JSON writers emit ``null``.

    The canonical contract forbids Python ``None`` in numeric slots, but JSON
    ``null`` is exactly what Grafana expects for "no measurement here".
    """
    if value is None:
        return math.nan
    return value


def flatten_parameter_name(prefix: tuple[str, ...], key: str) -> str:
    """Compose a unique slider-friendly name for a possibly nested key.

    The leading element of ``prefix`` is the *section* name (configuration /
    baseline_values / ...) and is intentionally dropped so that the same
    logical parameter merges across sections; nested container keys such as
    ``tensor_type_map`` are kept to disambiguate dynamic tensor names.
    """
    parts = [*prefix[1:], key] if prefix else [key]
    return "_".join(_DOTTED_KEY_RE.sub("_", str(part)) for part in parts if str(part))


def normalize_metric_name(param: str) -> str:
    """Metric ids may contain dots (e.g. ``wikitext.score``); sliders/fields
    need a single flat identifier."""
    return _DOTTED_KEY_RE.sub("_", param).strip("_")


# ---------------------------------------------------------------------------
# Experiment selection
# ---------------------------------------------------------------------------


def _pick_experiment(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Return the black box experiment that becomes model.json, or None for a legacy document.

    The contract with the frontend/black box team: ``model.json`` always keeps
    **the first experiment in the file** (``payload["experiments"][0]``), while
    every other run is archived into ``data/experiments/`` by
    :func:`split_black_box_payload`.  When the first entry carries no usable
    content at all (no metrics and no parameters), fall back to the most
    complete run so the API never serves an empty model.
    """
    candidates = _all_experiments(payload)
    if not candidates:
        return None
    primary = candidates[0]
    if _experiment_has_content(primary):
        return primary
    richest = max(candidates, key=_experiment_content_score)
    return richest if _experiment_has_content(richest) else primary


def _experiment_content_score(experiment: dict[str, Any]) -> int:
    score = 0
    metrics = experiment.get("metrics")
    if isinstance(metrics, list):
        score += sum(1 for item in metrics if isinstance(item, dict))
    for section in ("configuration", "critical_parameters", "baseline_values"):
        value = experiment.get(section)
        if isinstance(value, dict):
            score += len(value)
    return score


def _experiment_has_content(experiment: dict[str, Any]) -> bool:
    return _experiment_content_score(experiment) > 0


def _all_experiments(payload: dict[str, Any]) -> list[dict[str, Any]]:
    experiments = payload.get("experiments")
    if not isinstance(experiments, list):
        return []
    return [item for item in experiments if isinstance(item, dict)]


def is_black_box_payload(payload: dict[str, Any]) -> bool:
    return _pick_experiment(payload) is not None


# ---------------------------------------------------------------------------
# Meta extraction (schema-driven: model identifiers, bytes, timestamps)
# ---------------------------------------------------------------------------


def _model_name(identifier: Any, fallback: str) -> str:
    if isinstance(identifier, str) and identifier.strip():
        return identifier.strip()
    if isinstance(identifier, dict):
        for key in ("model_id", "variant", "artifact", "format"):
            value = identifier.get(key)
            if isinstance(value, str) and value.strip():
                name = value.strip()
                if key == "artifact":
                    name = Path(name).stem or name
                return name
    return fallback


# ---------------------------------------------------------------------------
# Parameter harvesting (fully schema-driven)
# ---------------------------------------------------------------------------


class _ParameterCollector:
    """Walks the black box experiment and harvests every scalar parameter.

    Sources merged per parameter name (first non-conflicting value wins):
    ``configuration`` (current value), ``critical_parameters.<name>.value``,
    ``baseline_values.<name>``, plus bounds from ``parameter_ranges`` and the
    wrapper flags (``critical``/``type``/``sensitivity``).  Nested objects such
    as ``tensor_type_map`` are expanded using *both* the schema-declared keys
    and the keys actually present in the payload, so nothing enumerated in
    ``schemas/`` is missed and future keys flow through automatically.
    """

    def __init__(self, experiment_node_schema: dict[str, Any]):
        self.schema = experiment_node_schema
        props = experiment_node_schema.get("properties", {})
        self.configuration_schema = props.get("configuration", {})
        self.critical_schema = props.get("critical_parameters", {})
        self.baseline_schema = props.get("baseline_values", {})
        self.ranges_schema = props.get("parameter_ranges", {})

    def collect(self, experiment: dict[str, Any]) -> dict[str, dict[str, Any]]:
        params: dict[str, dict[str, Any]] = {}

        def entry(name: str) -> dict[str, Any]:
            return params.setdefault(
                name, {"values": {}, "bounds": {}, "critical": False, "sensitivity": {}, "declared_type": None}
            )

        # 1) configuration section (includes nested tensor maps).
        config = experiment.get("configuration")
        known_config_keys = collect_object_keys(self.configuration_schema, recurse=True)
        if isinstance(config, dict):
            self._walk_mapping(
                config,
                prefix=("configuration",),
                schema=self.configuration_schema,
                known_keys=known_config_keys,
                sink=lambda name, value: entry(name)["values"].setdefault("configuration", value),
            )

        # 2) critical_parameters wrappers.
        critical_section = experiment.get("critical_parameters")
        if isinstance(critical_section, dict):
            for raw_name, definition in critical_section.items():
                if not isinstance(raw_name, str):
                    continue
                name = flatten_parameter_name(("critical_parameters",), raw_name)
                if isinstance(definition, dict) and ("value" in definition or "critical" in definition):
                    record = entry(name)
                    raw_value = definition.get("value")
                    record["values"].setdefault("critical", raw_value)
                    record["critical"] = record["critical"] or bool(definition.get("critical", False))
                    declared = definition.get("type")
                    if isinstance(declared, str):
                        record["declared_type"] = record["declared_type"] or declared
                    sensitivity = definition.get("sensitivity")
                    if isinstance(sensitivity, dict):
                        for metric_key, metric_value in sensitivity.items():
                            number = _as_float(metric_value)
                            if isinstance(metric_key, str) and number is not None:
                                record["sensitivity"][normalize_metric_name(metric_key)] = number
                elif isinstance(definition, dict):
                    # Wrapper without a plain "value" — treat as nested mapping.
                    self._walk_mapping(
                        definition,
                        prefix=("critical_parameters", raw_name),
                        schema=self.critical_schema.get("properties", {}).get(raw_name, {}),
                        known_keys=set(),
                        sink=lambda n, v: entry(n)["values"].setdefault("critical", v),
                    )
                else:
                    entry(name)["values"].setdefault("critical", definition)
                    entry(name)["critical"] = True

        # 3) baseline_values section.
        baselines = experiment.get("baseline_values")
        known_baseline_keys = collect_object_keys(self.baseline_schema, recurse=True)
        if isinstance(baselines, dict):
            self._walk_mapping(
                baselines,
                prefix=("baseline_values",),
                schema=self.baseline_schema,
                known_keys=known_baseline_keys,
                sink=lambda name, value: entry(name)["values"].setdefault("baseline", value),
            )

        # 4) parameter_ranges bounds.  A null bound simply stays absent —
        #    semantically it means "unbounded on this side" (kept, not dropped).
        ranges = experiment.get("parameter_ranges")
        if isinstance(ranges, dict):
            for raw_name, definition in ranges.items():
                if not isinstance(raw_name, str) or not isinstance(definition, dict):
                    continue
                name = flatten_parameter_name(("parameter_ranges",), raw_name)
                record = entry(name)
                low = _as_float(definition.get("min"))
                high = _as_float(definition.get("max"))
                if low is not None:
                    record["bounds"]["min"] = low
                if high is not None:
                    record["bounds"]["max"] = high
                # Remember explicit unboundedness for downstream consumers.
                if "min" in definition and definition.get("min") is None:
                    record["unbounded_min"] = True
                if "max" in definition and definition.get("max") is None:
                    record["unbounded_max"] = True

        # Resolve values: prefer configuration, then critical wrapper, then
        # baseline snapshot.  Numeric parameters become sliders; non-numeric
        # ones (quantization_method, tensor types, commits, ...) are NOT
        # dropped any more — they are kept as categorical/string entries so
        # the parameter count matches the source file.  Only parameters whose
        # value is missing entirely (null/"N/A" everywhere) or that are pure
        # containers without scalar leaves are skipped.
        resolved: dict[str, dict[str, Any]] = {}
        for name, record in params.items():
            raw_value = None
            declared = record.get("declared_type")
            for source in ("configuration", "critical", "baseline"):
                candidate = record["values"].get(source)
                if _is_meaningful(candidate):
                    raw_value = candidate
                    break
            if raw_value is None:
                continue
            entry = {**record, "raw_value": raw_value}
            number = _as_float(raw_value)
            if number is not None and not (declared == "string"):
                entry["value"] = number
                entry["kind"] = "number"
            elif isinstance(raw_value, bool) or declared == "boolean":
                entry["value"] = float(bool(raw_value))
                entry["kind"] = "boolean"
            else:
                text = str(raw_value).strip()
                if not text:
                    continue
                entry["value"] = None
                entry["kind"] = "string"
                entry["text"] = text
            resolved[name] = entry
        return resolved

    def _walk_mapping(
        self,
        mapping: dict[str, Any],
        *,
        prefix: tuple[str, ...],
        schema: Any,
        known_keys: set[str],
        sink,
    ) -> None:
        """Recurse into nested dicts (e.g. tensor_type_map) flattening keys.

        Keys come from the payload; ``known_keys`` (the schema enumeration) is
        used to recognize already-flattened names so that logical parameters
        merge across sections regardless of which representation the black box
        chose.  Schema-only keys with no payload counterpart carry no value and
        are therefore not invented here — they simply never appear.
        """
        schema_props = schema.get("properties") if isinstance(schema, dict) else None
        flattened_index: dict[str, str] = {}
        for key in mapping:
            if isinstance(key, str):
                flattened_index.setdefault(flatten_parameter_name(prefix, key), key)
        # Schema-declared keys absent from the payload may still be present
        # under their flattened spelling (defensive against double encoding).
        for schema_key in known_keys:
            if schema_key in mapping or not isinstance(schema_key, str):
                continue
            target = flatten_parameter_name(prefix, schema_key)
            if target in flattened_index:
                mapping[schema_key] = mapping[flattened_index[target]]
        for key in sorted(mapping):
            if key in _META_KEYS:
                continue
            child_schema = (schema_props or {}).get(key, {})
            name = flatten_parameter_name(prefix, key)
            value = mapping[key]
            if isinstance(value, dict):
                nested_known = collect_object_keys(child_schema) if child_schema else set()
                self._walk_mapping(
                    value,
                    prefix=(*prefix, key),
                    schema=child_schema,
                    known_keys=nested_known,
                    sink=sink,
                )
            else:
                sink(name, value)


# ---------------------------------------------------------------------------
# Metrics conversion with universal null handling
# ---------------------------------------------------------------------------


def _metric_param(metric: dict[str, Any]) -> str:
    param = metric.get("param")
    if isinstance(param, str) and param.strip():
        return param.strip()
    name = metric.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    dataset = metric.get("dataset")
    if isinstance(dataset, str) and dataset.strip():
        return f"{dataset}_score"
    return "metric"


def _cross_experiment_fallback(
    all_experiments: list[dict[str, Any]], param: str, side: str
) -> float | None:
    """Find the missing metric side in sibling runs of the same document.

    Black box runs often measure the full-model baseline once and reuse it;
    when the selected run stores ``null`` we recover the number from another
    experiment that reported the same ``param``/side as a finite value.
    """
    for experiment in all_experiments:
        metrics = experiment.get("metrics")
        if not isinstance(metrics, list):
            continue
        for item in metrics:
            if not isinstance(item, dict):
                continue
            if normalize_metric_name(_metric_param(item)) != param:
                continue
            number = _as_float(item.get(side))
            if number is not None:
                return number
    return None


def _convert_metrics(
    metrics: Any,
    *,
    siblings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    seen: set[str] = set()
    if not isinstance(metrics, list):
        return converted
    for item in metrics:
        if not isinstance(item, dict):
            continue
        param = normalize_metric_name(_metric_param(item))
        if param in seen:
            continue
        seen.add(param)
        values: dict[str, float | None] = {}
        for side in ("full", "compressed"):
            number = _as_float(item.get(side))
            if number is None:
                # Universal null policy: first try to recover the number from
                # sibling runs, then keep the slot as JSON null (NaN) so the
                # metric itself is never silently dropped.
                number = _cross_experiment_fallback(siblings, param, side)
            values[side] = number
        if all(value is None for value in values.values()):
            # Nothing measurable at all — cannot fabricate a comparison point.
            continue
        converted.append(
            {
                "param": param,
                "full": _json_number(values["full"]),
                "compressed": _json_number(values["compressed"]),
            }
        )
    return converted


def _convert_per_class(per_class: Any) -> list[Any]:
    return [item for item in per_class if isinstance(item, dict)] if isinstance(per_class, list) else []


# ---------------------------------------------------------------------------
# Public conversion API
# ---------------------------------------------------------------------------


def convert_black_box_experiment(
    experiment: dict[str, Any],
    *,
    siblings: list[dict[str, Any]] | None = None,
    schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Transform one black box experiment object into the comparison.json shape."""
    schema = schema or load_cached_schema("black_box_experiments_schema.json")
    experiment_node = experiment_schema_node(schema)
    props = experiment_node.get("properties", {})

    collector = _ParameterCollector(experiment_node)
    params = collector.collect(experiment)

    names = sorted(params)
    configuration = {name: params[name]["value"] for name in names if params[name]["kind"] != "string"}
    critical_parameters: dict[str, dict[str, Any]] = {}
    for name in names:
        record = params[name]
        entry: dict[str, Any] = {"critical": bool(record.get("critical", False))}
        entry["baseline"] = record["value"]
        if record.get("declared_type"):
            entry["type"] = record["declared_type"]
        entry["kind"] = record["kind"]
        if record["kind"] == "string":
            # Non-numeric parameter: kept for completeness of the parameter
            # list (and visible to the UI as a fixed value), but it never
            # enters the numeric slider contract.
            entry["value"] = record["text"]
        bounds = record.get("bounds", {})
        if "min" in bounds:
            entry["min"] = bounds["min"]
        if "max" in bounds:
            entry["max"] = bounds["max"]
        if record.get("sensitivity"):
            entry["sensitivity"] = dict(record["sensitivity"])
        critical_parameters[name] = entry

    meta: dict[str, Any] = {
        "full_model": _model_name(experiment.get("full_model_identifier"), "full_model"),
        "compressed_model": _model_name(
            experiment.get("compressed_model_identifier"), "compressed_model"
        ),
        "timestamp": str(experiment.get("timestamp") or ""),
        "model_id": str(experiment.get("experiment_id") or "").strip(),
    }
    converted: dict[str, Any] = {"experiment_id": str(experiment.get("experiment_id") or "").strip(), "meta": meta,
                                 "configuration": configuration, "critical_parameters": critical_parameters,
                                 "metrics": _convert_metrics(
                                     experiment.get("metrics"),
                                     siblings=[sibling for sibling in (siblings or []) if sibling is not experiment],
                                 ), "per_class": _convert_per_class(experiment.get("per_class")),
                                 "source_experiment": experiment}
    # Keep an immutable snapshot of the original run so nothing from the black
    # box output is lost by the projection above (BLK-008: preserve extras).
    return converted


def preprocess_raw_payload(payload: Any) -> Any:
    """Backend entry point: normalize any accepted input to the comparison shape.

    * dict containing ``experiments`` -> convert the **first** black box run;
    * anything else (already canonical comparison.json) -> returned unchanged.
    """
    if not isinstance(payload, dict):
        return payload
    experiment = _pick_experiment(payload)
    if experiment is None:
        return payload
    return convert_black_box_experiment(experiment, siblings=_all_experiments(payload))


def split_black_box_payload(payload: Any) -> list[dict[str, Any]]:
    """Convert **every** experiment of a black box document, in file order.

    Returns one comparison-shaped dict per run; the first element corresponds
    to ``payload["experiments"][0]`` and is what model.json receives, while the
    remaining runs are archived into ``data/experiments/`` by the store.  Each
    run still sees all sibling runs, so missing metric sides are recovered from
    other experiments of the same document.  Legacy/canonical documents yield
    an empty list (nothing to split).
    """
    if not isinstance(payload, dict):
        return []
    experiments = _all_experiments(payload)
    if not experiments:
        return []
    schema = load_cached_schema("black_box_experiments_schema.json")
    return [
        convert_black_box_experiment(experiment, siblings=experiments, schema=schema)
        for experiment in experiments
    ]


__all__ = [
    "convert_black_box_experiment",
    "flatten_parameter_name",
    "is_black_box_payload",
    "load_comparison_schema",
    "preprocess_raw_payload",
    "split_black_box_payload",
]


def load_comparison_schema() -> dict[str, Any]:
    return load_schema("comparison_schema.json")
