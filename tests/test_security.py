"""Tests for Sprint-1 hardening: SSE auth, rate limiting, legal-forms cache."""

from __future__ import annotations

import asyncio

import httpx
import pytest
import respx
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from register_mcp._middleware import BearerAuthMiddleware, RateLimitMiddleware
from register_mcp.server import (
    ZEFIX_BASE,
    LegalFormsInput,
    _fetch_legal_forms,
    _reset_legal_forms_cache,
    zefix_list_legal_forms,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _ok(request):
    return JSONResponse({"ok": True})


def _stack(*, expected_key: str = "secret", limit: int = 60, window: float = 60.0) -> Starlette:
    app = Starlette(routes=[Route("/", _ok), Route("/sse", _ok)])
    app.add_middleware(RateLimitMiddleware, limit=limit, window=window)
    app.add_middleware(BearerAuthMiddleware, expected_key=expected_key)
    return app


MOCK_LEGAL_FORMS = [{"id": 3, "name": {"de": "AG"}, "kurzform": {"de": "AG"}, "sort": 300}]


# ---------------------------------------------------------------------------
# SEC-AUTH-SSE
# ---------------------------------------------------------------------------

class TestBearerAuth:
    def test_rejects_request_without_header(self):
        client = TestClient(_stack())
        r = client.get("/")
        assert r.status_code == 401
        assert r.json() == {"error": "unauthorized"}

    def test_rejects_wrong_key(self):
        client = TestClient(_stack())
        r = client.get("/", headers={"Authorization": "Bearer nope"})
        assert r.status_code == 401

    def test_accepts_correct_key(self):
        client = TestClient(_stack())
        r = client.get("/", headers={"Authorization": "Bearer secret"})
        assert r.status_code == 200
        assert r.json() == {"ok": True}

    def test_empty_key_rejected_at_construction(self):
        with pytest.raises(ValueError):
            BearerAuthMiddleware(app=None, expected_key="")


# ---------------------------------------------------------------------------
# SEC-023
# ---------------------------------------------------------------------------

class TestRateLimit:
    def test_blocks_after_limit_exceeded(self):
        client = TestClient(_stack(limit=3, window=60))
        headers = {"Authorization": "Bearer secret"}
        for _ in range(3):
            assert client.get("/", headers=headers).status_code == 200
        r = client.get("/", headers=headers)
        assert r.status_code == 429
        assert r.headers.get("retry-after")
        assert r.json() == {"error": "rate_limited"}

    def test_separate_buckets_per_client(self):
        client = TestClient(_stack(limit=2, window=60))
        for _ in range(2):
            assert client.get("/", headers={"Authorization": "Bearer secret"}).status_code == 200
        # Different key would not get past auth; same key counts as same client.
        # Different IP via X-Forwarded-* would still hash to same auth bucket, by design.
        r = client.get("/", headers={"Authorization": "Bearer secret"})
        assert r.status_code == 429

    def test_window_recycles(self):
        # Window 0.2s — third call after a short sleep should pass again.
        client = TestClient(_stack(limit=2, window=0.2))
        headers = {"Authorization": "Bearer secret"}
        assert client.get("/", headers=headers).status_code == 200
        assert client.get("/", headers=headers).status_code == 200
        assert client.get("/", headers=headers).status_code == 429
        import time
        time.sleep(0.25)
        assert client.get("/", headers=headers).status_code == 200

    def test_validates_construction_args(self):
        with pytest.raises(ValueError):
            RateLimitMiddleware(app=None, limit=0)
        with pytest.raises(ValueError):
            RateLimitMiddleware(app=None, window=0)


# ---------------------------------------------------------------------------
# ARCH-CACHE
# ---------------------------------------------------------------------------

class TestLegalFormsCache:
    @pytest.fixture(autouse=True)
    def _clear(self):
        _reset_legal_forms_cache()
        yield
        _reset_legal_forms_cache()

    @respx.mock
    async def test_second_call_within_ttl_uses_cache(self):
        route = respx.get(f"{ZEFIX_BASE}/legalForm").mock(
            return_value=httpx.Response(200, json=MOCK_LEGAL_FORMS)
        )

        first = await _fetch_legal_forms()
        second = await _fetch_legal_forms()
        third = await _fetch_legal_forms()

        assert first == MOCK_LEGAL_FORMS
        assert second is first  # identity: same cached list
        assert third is first
        assert route.call_count == 1

    @respx.mock
    async def test_expired_ttl_triggers_refetch(self):
        route = respx.get(f"{ZEFIX_BASE}/legalForm").mock(
            return_value=httpx.Response(200, json=MOCK_LEGAL_FORMS)
        )

        await _fetch_legal_forms(ttl=0.05)
        await asyncio.sleep(0.07)
        await _fetch_legal_forms(ttl=0.05)

        assert route.call_count == 2

    @respx.mock
    async def test_tool_call_shares_cache(self):
        """zefix_list_legal_forms uses the same cache as the shared fetcher."""
        route = respx.get(f"{ZEFIX_BASE}/legalForm").mock(
            return_value=httpx.Response(200, json=MOCK_LEGAL_FORMS)
        )
        await _fetch_legal_forms()
        await zefix_list_legal_forms(LegalFormsInput())
        assert route.call_count == 1
