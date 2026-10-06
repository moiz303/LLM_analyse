from __future__ import annotations

import json
import math
from typing import Any


def nan_to_none(value: Any) -> Any:
    """Recursively replace NaN/Infinity floats with ``None`` (JSON ``null``).

    The preprocess layer intentionally encodes "no measurement" as ``math.nan``
    so writers can emit JSON ``null`` via ``allow_nan=True``.  FastAPI's default
    response serializer uses strict JSON (``allow_nan=False``), which raises
    ``ValueError: Out of range float values are not JSON compliant: nan`` and
    turns the endpoint into a 500 for the browser.  Normalizing NaN to None
    keeps the documented contract ("null means no measurement") on the wire.
    """
    if isinstance(value, float):
        return None if not math.isfinite(value) else value
    if isinstance(value, dict):
        return {key: nan_to_none(item) for key, item in value.items()}
    if isinstance(value, list):
        return [nan_to_none(item) for item in value]
    if isinstance(value, tuple):
        return [nan_to_none(item) for item in value]
    return value


def dump_json_string(value: Any, **kwargs: Any) -> str:
    kwargs.setdefault("ensure_ascii", False)
    kwargs.setdefault("default", str)
    return json.dumps(nan_to_none(value), allow_nan=False, **kwargs)


__all__ = ["dump_json_string", "nan_to_none"]