"""Shared HTTP resilience helpers for external data providers.

Providers historically failed open on transient errors: a single 429 or
timeout dropped the whole batch, and Retry-After headers were parsed with
``isdigit()`` (rejecting decimals and HTTP-dates). These helpers give every
provider the same bounded-retry behavior with server-honoring backoff.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from time import monotonic

import httpx

RETRY_ATTEMPTS = 3
MAX_BACKOFF_SECONDS = 8.0


def retry_after_seconds(header: str | None, attempt: int) -> float:
    """Translate a Retry-After header (seconds or HTTP-date) into a delay."""
    if header:
        try:
            return max(0.0, float(header))
        except ValueError:
            pass
        try:
            target = parsedate_to_datetime(header)
        except (TypeError, ValueError, OverflowError):
            target = None
        if target is not None:
            if target.tzinfo is None:
                target = target.replace(tzinfo=UTC)
            wait = (target - datetime.now(UTC)).total_seconds()
            if wait > 0:
                return wait
    return min(1.0 * (2**attempt), MAX_BACKOFF_SECONDS)


async def request_with_retries(
    client: httpx.AsyncClient,
    url: str,
    params: dict,
    *,
    attempts: int = RETRY_ATTEMPTS,
) -> httpx.Response:
    """GET with bounded retries on 429/5xx and transport errors.

    Client errors (4xx other than 429) fail immediately — retrying them
    cannot succeed.
    """
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = await client.get(url, params=params)
            if response.status_code == 429 or response.status_code >= 500:
                last_error = RuntimeError(
                    f"{url} returned HTTP {response.status_code}"
                )
                if attempt == attempts - 1:
                    break
                delay = retry_after_seconds(response.headers.get("Retry-After"), attempt)
                await asyncio.sleep(min(delay, 65.0))
                continue
            response.raise_for_status()
            return response
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            last_error = exc
            if attempt == attempts - 1:
                break
            await asyncio.sleep(min(1.0 * (2**attempt), MAX_BACKOFF_SECONDS))
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"{url} failed after {attempts} attempts")


class SlidingWindowLimiter:
    """Client-side throttle so bursts never exceed a provider quota.

    OpenAQ rate-limits per minute; issuing 60 city requests inside a few
    seconds guarantees 429s. Holding a small sliding window in the provider
    spreads calls without changing call sites.
    """

    def __init__(self, max_calls: int, per_seconds: float):
        self.max_calls = max_calls
        self.per_seconds = per_seconds
        self._timestamps: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                now = monotonic()
                self._timestamps = [
                    ts for ts in self._timestamps if now - ts < self.per_seconds
                ]
                if len(self._timestamps) < self.max_calls:
                    self._timestamps.append(now)
                    return
                wait = self.per_seconds - (now - self._timestamps[0])
            await asyncio.sleep(max(wait, 0.05) + 0.01)
