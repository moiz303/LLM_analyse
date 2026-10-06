from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

def _candidate_schemas_dirs() -> list[Path]:
    """Schema directories to probe, in order of preference.

    ``SCHEMAS_DIR`` (env var) always wins; otherwise we walk upward from this
    file and accept any ancestor that contains a ``schemas/`` folder.  This
    covers both layouts:

    * repository checkout: ``backend/app/services`` -> repo root ``schemas/``;
    * container image: ``/app/backend/...`` -> ``/app/schemas`` (the schemas
      are copied next to ``data`` by the Dockerfile).
    """
    env_dir = os.environ.get("SCHEMAS_DIR")
    if env_dir:
        return [Path(env_dir)]
    here = Path(__file__).resolve()
    return [parent / "schemas" for parent in here.parents]


def resolve_schemas_dir() -> Path:
    """Return the first existing schemas directory or raise a clear error."""
    candidates = _candidate_schemas_dirs()
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(
        "JSON Schema directory not found. Looked in: "
        + ", ".join(str(path) for path in candidates[:4])
        + ". Set the SCHEMAS_DIR environment variable or mount/copy the "
        "'schemas' folder next to the application root."
    )


def load_schema(name: str) -> dict[str, Any]:
    path = resolve_schemas_dir() / name
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=None)
def load_cached_schema(name: str) -> dict[str, Any]:
    """Same as :func:`load_schema` but memoized (schemas never change at runtime)."""
    return load_schema(name)


def iter_schema_variants(node: Any) -> Iterator[dict[str, Any]]:
    """Yield object variants describing the items of an array schema node."""
    if not isinstance(node, dict):
        return
    items = node.get("items")
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                yield item
    elif isinstance(items, dict):
        yield items


def _scalar_types(declaration: Any) -> set[str]:
    if not isinstance(declaration, dict):
        return set()
    declared = declaration.get("type")
    if isinstance(declared, str):
        return {declared}
    if isinstance(declared, list):
        return {entry for entry in declared if isinstance(entry, str)}
    return set()


def collect_field_types(node: Any, field: str) -> set[str]:
    """Union of declared types of ``field`` across every variant of ``node``."""
    types: set[str] = set()
    for variant in iter_schema_variants(node):
        types |= _scalar_types(variant.get("properties", {}).get(field))
    return types


def is_nullable_field(node: Any, field: str) -> bool:
    return "null" in collect_field_types(node, field)


def collect_object_keys(node: Any, *, recurse: bool = False) -> set[str]:
    """Known property names of an object schema (across all its variants)."""
    keys: set[str] = set()
    variants = list(iter_schema_variants(node)) or (
        [node] if isinstance(node, dict) and "properties" in node else []
    )
    for variant in variants:
        properties = variant.get("properties")
        if not isinstance(properties, dict):
            continue
        for key, declaration in properties.items():
            if not isinstance(key, str):
                continue
            keys.add(key)
            if recurse and isinstance(declaration, dict) and "properties" in declaration:
                keys |= collect_object_keys(declaration, recurse=True)
    return keys


def experiment_schema_node(black_box_schema: dict[str, Any]) -> dict[str, Any]:
    """The schema describing one entry of the black box ``experiments`` array."""
    node: Any = black_box_schema.get("properties", {}).get("experiments", {})
    variants = list(iter_schema_variants(node))
    return variants[0] if variants else {}


__all__ = [
    "SCHEMAS_DIR",
    "collect_field_types",
    "collect_object_keys",
    "experiment_schema_node",
    "is_nullable_field",
    "iter_schema_variants",
    "load_cached_schema",
    "load_schema",
]
