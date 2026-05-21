"""ASGI middleware for the SSE transport: bearer-token auth and rate limiting."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
from collections import defaultdict
from time import monotonic
from typing import Any

from ._log import log_event

_ASGIApp = Any


def _send_json(status: int, body: bytes, extra_headers: list[tuple[bytes, bytes]] | None = None):
    headers: list[tuple[bytes, bytes]] = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode()),
    ]
    if extra_headers:
        headers.extend(extra_headers)

    async def respond(send):
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})

    return respond


class BearerAuthMiddleware:
    """Reject requests without a matching `Authorization: Bearer <key>` header.

    Constant-time comparison via hmac.compare_digest to avoid timing leaks.
    Non-HTTP scopes (lifespan, websocket) pass through unchanged.
    """

    def __init__(self, app: _ASGIApp, expected_key: str) -> None:
        if not expected_key:
            raise ValueError("BearerAuthMiddleware requires a non-empty expected_key")
        self.app = app
        self._expected = f"Bearer {expected_key}".encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        provided = b""
        for name, value in scope.get("headers", []):
            if name == b"authorization":
                provided = value
                break
        if not hmac.compare_digest(provided, self._expected):
            log_event(
                logging.WARNING,
                "auth_failed",
                path=scope.get("path"),
                client=scope.get("client", ["?"])[0],
            )
            respond = _send_json(401, b'{"error":"unauthorized"}')
            await respond(send)
            return
        await self.app(scope, receive, send)


class RateLimitMiddleware:
    """Sliding-window in-memory rate limit per client (Authorization header hash).

    Default: 60 requests per 60 seconds. Returns HTTP 429 with Retry-After when exceeded.
    Intended for single-instance deployments; for multi-instance use a Gateway or Redis.
    """

    def __init__(self, app: _ASGIApp, limit: int = 60, window: float = 60.0) -> None:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if window <= 0:
            raise ValueError("window must be > 0")
        self.app = app
        self.limit = limit
        self.window = window
        self._buckets: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    @staticmethod
    def _client_id(scope) -> str:
        auth = b""
        for name, value in scope.get("headers", []):
            if name == b"authorization":
                auth = value
                break
        if auth:
            return hashlib.sha256(auth).hexdigest()[:16]
        client = scope.get("client") or ("anon", 0)
        return f"ip:{client[0]}"

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        cid = self._client_id(scope)
        now = monotonic()
        cutoff = now - self.window
        async with self._lock:
            bucket = self._buckets[cid]
            # Drop expired timestamps from the head.
            i = 0
            for ts in bucket:
                if ts >= cutoff:
                    break
                i += 1
            if i:
                del bucket[:i]
            if len(bucket) >= self.limit:
                retry_after = max(1, int(self.window - (now - bucket[0])))
                log_event(
                    logging.WARNING,
                    "rate_limited",
                    client=cid,
                    limit=self.limit,
                    window=self.window,
                )
                respond = _send_json(
                    429,
                    b'{"error":"rate_limited"}',
                    extra_headers=[(b"retry-after", str(retry_after).encode())],
                )
                await respond(send)
                return
            bucket.append(now)
        await self.app(scope, receive, send)
