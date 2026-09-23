from __future__ import annotations

from collections.abc import Sequence


def persistence(history: Sequence[float], horizon: int = 1) -> list[float]:
    if not history:
        raise ValueError("history must not be empty")
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    return [float(history[-1])] * horizon

def rolling_mean(history: Sequence[float], horizon: int = 1, window: int = 6) -> list[float]:
    if not history:
        raise ValueError("history must not be empty")
    if horizon < 1 or window < 1:
        raise ValueError("horizon and window must be >= 1")
    values = [float(v) for v in history[-window:]]
    mean = sum(values) / len(values)
    return [mean] * horizon
