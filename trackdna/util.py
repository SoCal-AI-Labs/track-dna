from __future__ import annotations

from typing import Any

import numpy as np


def db(x: float, floor: float = 1e-12) -> float:
    return float(20.0 * np.log10(max(float(x), floor)))


def power_db(x: float, floor: float = 1e-12) -> float:
    return float(10.0 * np.log10(max(float(x), floor)))


def safe_div(num: float, den: float, default: float = 0.0) -> float:
    if abs(den) < 1e-12:
        return default
    return float(num / den)


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
        return None
    return value


def clamp(x: float, lo: float, hi: float) -> float:
    return float(min(hi, max(lo, x)))


def nearest(times: np.ndarray, t: float) -> float:
    if times.size == 0:
        return float(t)
    idx = int(np.argmin(np.abs(times - t)))
    return float(times[idx])
