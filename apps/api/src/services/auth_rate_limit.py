"""In-process auth rate limiting (Phase B)."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status


class AuthRateLimiter:
    """Sliding-window limiter keyed by client ip + action + email."""

    def __init__(self, *, max_attempts: int = 10, window_seconds: float = 300.0) -> None:
        self._max_attempts = max(1, int(max_attempts))
        self._window_seconds = max(1.0, float(window_seconds))
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def configure(self, *, max_attempts: int, window_seconds: float) -> None:
        with self._lock:
            self._max_attempts = max(1, int(max_attempts))
            self._window_seconds = max(1.0, float(window_seconds))

    def reset(self) -> None:
        with self._lock:
            self._events.clear()

    def check(self, *, request: Request, action: str, email: str) -> None:
        key = f"{_client_ip(request)}|{action}|{email.strip().lower()}"
        now = time.monotonic()
        with self._lock:
            bucket = self._events[key]
            while bucket and (now - bucket[0]) > self._window_seconds:
                bucket.popleft()
            if len(bucket) >= self._max_attempts:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many auth attempts. Try again later.",
                )
            bucket.append(now)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if forwarded:
        return forwarded
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


# Process-wide limiter for login/register/refresh/invite-accept.
auth_rate_limiter = AuthRateLimiter(max_attempts=10, window_seconds=300.0)
