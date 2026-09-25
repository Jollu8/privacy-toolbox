"""Strict JSON operations with useful parser locations."""
import json
import math


def _invalid_constant(value):
    raise ValueError(f"{value} is not a valid JSON value.")


def _finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Number is outside the supported floating-point range.")
    return number


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate object key: {key!r}. Resolve it before formatting.")
        result[key] = value
    return result


def transform(text: str, mode: str = "format", indent: int = 2, sort_keys: bool = False) -> dict:
    if mode not in {"format", "minify", "validate", "sort"}:
        raise ValueError("Choose a supported JSON operation.")
    value = parse_json(text)
    if mode == "validate":
        return {"text": "Valid JSON. No syntax errors or duplicate keys found."}
    # allow_nan=False also rejects numeric overflow such as 1e999.
    return {"text": json.dumps(value, ensure_ascii=False, allow_nan=False,
                               indent=None if mode == "minify" else indent,
                               separators=(",", ":") if mode == "minify" else None,
                               sort_keys=sort_keys or mode == "sort")}


def parse_json(text):
    try:
        return json.loads(text, parse_constant=_invalid_constant, parse_float=_finite_float, object_pairs_hook=_unique_object)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{exc.msg} (line {exc.lineno}, column {exc.colno}).") from exc
