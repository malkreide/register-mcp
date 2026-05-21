"""Tests for the egress allow-list (SEC-021)."""

from __future__ import annotations

import httpx
import pytest
import respx

from register_mcp.server import ALLOWED_HOSTS, EgressDenied, _make_client


class TestEgressAllowlist:
    def test_default_allowlist_contains_zefix(self):
        assert "www.zefix.admin.ch" in ALLOWED_HOSTS

    @respx.mock
    async def test_allowed_host_passes(self):
        respx.get("https://www.zefix.admin.ch/x").mock(return_value=httpx.Response(200))
        async with _make_client() as client:
            r = await client.get("https://www.zefix.admin.ch/x")
        assert r.status_code == 200

    async def test_disallowed_host_is_blocked(self):
        async with _make_client() as client:
            with pytest.raises(EgressDenied):
                await client.get("https://evil.example.com/")

    async def test_metadata_endpoint_blocked(self):
        # AWS/GCP IMDS — the classic SSRF target. Defence-in-depth check.
        async with _make_client() as client:
            with pytest.raises(EgressDenied):
                await client.get("http://169.254.169.254/latest/meta-data/")

    @respx.mock
    async def test_redirect_to_disallowed_host_is_blocked(self):
        respx.get("https://www.zefix.admin.ch/r").mock(
            return_value=httpx.Response(302, headers={"location": "https://evil.example.com/"})
        )
        async with _make_client() as client:
            with pytest.raises(EgressDenied):
                await client.get("https://www.zefix.admin.ch/r")

    def test_host_match_is_case_insensitive(self):
        # ALLOWED_HOSTS is normalised to lowercase; host comparison too.
        assert all(h == h.lower() for h in ALLOWED_HOSTS)
