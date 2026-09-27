"""Streamable HTTP: der Transport, ueber den Spec 2026-07-28 HTTP spricht.

Bis hierhin konnte `tests/test_protocol_version.py` nur SDK-Konstanten
zusichern — dieses Repo baute keine ASGI-App, durch die sich eine Anfrage
schicken liess, und die SSE-App erreicht die moderne Aera nicht. Die Tests
hier schicken echte JSON-RPC-Koerper durch genau die App, die `main()` mit
`MCP_TRANSPORT=streamable-http` startet, und lesen die Antwort.

Eine 2026-07-28-Anfrage ist ein einzelner POST: `_meta`-Envelope im Koerper,
`MCP-Protocol-Version` und `Mcp-Method` (bei `tools/call` auch `Mcp-Name`) im
Kopf, kein `initialize`, keine `Mcp-Session-Id`. Fehlt ein Kopf oder
widerspricht er dem Koerper, weist das SDK die Anfrage mit HTTP 400 ab — der
Grund, warum die Kopfzeilen hier mitgeschickt und nicht weggelassen werden.

Das SDK laesst den Lebenszyklus einer App nur einmal laufen; jeder Test baut
deshalb seine eigene ueber `_build_streamable_http_app()`.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from fixture_data import fixture_json
from mcp.types.version import LATEST_HANDSHAKE_VERSION
from starlette.testclient import TestClient

from register_mcp.server import (
    LIST_CACHE_TTL_MS,
    STREAMABLE_HTTP_PATH,
    ZEFIX_BASE,
    _build_sse_app,
    _build_streamable_http_app,
    _reset_legal_forms_cache,
    mcp,
)

MODERN = "2026-07-28"
API_KEY = "test-key"
# Ein oeffentlicher Hostname, wie ihn ein Container hinter einem Reverse-Proxy
# sieht. `testserver`, die Vorgabe von TestClient, wuerde den Fehler unten
# nicht zeigen: er steht auf keiner der beiden Listen, faellt aber genauso.
PUBLIC_HOST = "http://register-mcp.example.com"

META = {
    "io.modelcontextprotocol/protocolVersion": MODERN,
    "io.modelcontextprotocol/clientInfo": {"name": "pytest", "version": "0"},
    "io.modelcontextprotocol/clientCapabilities": {},
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("MCP_API_KEY", API_KEY)
    with TestClient(_build_streamable_http_app(), base_url=PUBLIC_HOST) as c:
        yield c


def _modern(
    client: TestClient, method: str, params: dict | None = None, name: str | None = None
) -> httpx.Response:
    headers = {
        "authorization": f"Bearer {API_KEY}",
        "accept": "application/json, text/event-stream",
        "mcp-protocol-version": MODERN,
        "mcp-method": method,
    }
    if name is not None:
        headers["mcp-name"] = name
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": {**(params or {}), "_meta": META},
    }
    return client.post(STREAMABLE_HTTP_PATH, headers=headers, json=body)


# ---------------------------------------------------------------------------
# Die moderne Aera, gemessen
# ---------------------------------------------------------------------------


def test_server_discover_nennt_2026_07_28(client):
    r = _modern(client, "server/discover")
    assert r.status_code == 200, r.text
    result = r.json()["result"]
    assert MODERN in result["supportedVersions"]
    assert result["_meta"]["io.modelcontextprotocol/serverInfo"]["version"] == mcp.version


def test_tools_list_traegt_die_frischehinweise_auf_dem_draht(client):
    """`test_cache_hints.py` prueft die Konfiguration; hier steht, was ankommt."""
    r = _modern(client, "tools/list")
    assert r.status_code == 200, r.text
    result = r.json()["result"]
    assert result["ttlMs"] == LIST_CACHE_TTL_MS
    assert result["cacheScope"] == "public"
    names = {t["name"] for t in result["tools"]}
    assert "zefix_get_company_by_uid" in names
    assert "gazette_company_publications" in names


@respx.mock
def test_tools_call_laeuft_ueber_den_modernen_einstieg(client):
    _reset_legal_forms_cache()
    legal_forms = fixture_json("zefix_legal_forms.json")
    route = respx.get(f"{ZEFIX_BASE}/legalForm").mock(
        return_value=httpx.Response(200, json=legal_forms)
    )
    try:
        r = _modern(
            client,
            "tools/call",
            {
                "name": "zefix_list_legal_forms",
                "arguments": {"params": {"response_format": "json"}},
            },
            name="zefix_list_legal_forms",
        )
    finally:
        _reset_legal_forms_cache()
    assert r.status_code == 200, r.text
    result = r.json()["result"]
    assert not result.get("isError"), result
    payload = json.loads(result["content"][0]["text"])
    assert {lf["id"] for lf in payload} == {lf["id"] for lf in legal_forms}
    assert route.call_count == 1


def test_fehlender_mcp_method_kopf_wird_abgewiesen(client):
    """Die Absage des SDK, nicht unsere — gepinnt, damit der Test oben nicht
    still an einer Stelle vorbeiprueft, die gar nicht erreicht wird."""
    r = client.post(
        STREAMABLE_HTTP_PATH,
        headers={
            "authorization": f"Bearer {API_KEY}",
            "accept": "application/json, text/event-stream",
            "mcp-protocol-version": MODERN,
        },
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"_meta": META}},
    )
    assert r.status_code == 400


def test_eine_unbekannte_revision_bekommt_die_unterstuetzte_genannt(client):
    future = "2099-01-01"
    r = client.post(
        STREAMABLE_HTTP_PATH,
        headers={
            "authorization": f"Bearer {API_KEY}",
            "accept": "application/json, text/event-stream",
            "mcp-protocol-version": future,
            "mcp-method": "tools/list",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {"_meta": {**META, "io.modelcontextprotocol/protocolVersion": future}},
        },
    )
    assert r.status_code == 400
    data = r.json()["error"]["data"]
    assert data["requested"] == future
    assert MODERN in data["supported"]


# ---------------------------------------------------------------------------
# Die Handshake-Aera auf demselben Endpunkt
# ---------------------------------------------------------------------------


def test_initialize_deckelt_bei_der_handshake_obergrenze(client):
    """Gemessen statt aus der Konstante geschlossen: wer Neueres verlangt,
    bekommt die Obergrenze des Handshakes, nicht die moderne Revision."""
    r = client.post(
        STREAMABLE_HTTP_PATH,
        headers={
            "authorization": f"Bearer {API_KEY}",
            "accept": "application/json, text/event-stream",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2099-01-01",
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "0"},
            },
        },
    )
    assert r.status_code == 200, r.text
    result = r.json()["result"]
    assert result["protocolVersion"] == LATEST_HANDSHAKE_VERSION
    assert result["serverInfo"]["version"] == mcp.version


def test_handshake_pfad_ist_zustandslos_und_antwortet_json(client):
    """Die beiden Flags wirken nur hier: der moderne Einstieg ist ohnehin
    zustandslos und antwortet einem schnellen Handler ohnehin mit JSON.

    `stateless_http=True` — keine `Mcp-Session-Id`, also keine Sitzung im
    Speicher eines einzelnen Containers. `json_response=True` — kein Tool
    meldet Fortschritt oder fragt zurueck, ein Ereignisstrom truege nichts.
    """
    r = client.post(
        STREAMABLE_HTTP_PATH,
        headers={
            "authorization": f"Bearer {API_KEY}",
            "accept": "application/json, text/event-stream",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": LATEST_HANDSHAKE_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "0"},
            },
        },
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/json")
    assert "mcp-session-id" not in r.headers


# ---------------------------------------------------------------------------
# Absicherung — dieselbe wie bei SSE
# ---------------------------------------------------------------------------


def test_ohne_token_401(client):
    r = client.post(
        STREAMABLE_HTTP_PATH,
        headers={"mcp-protocol-version": MODERN, "mcp-method": "tools/list"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"_meta": META}},
    )
    assert r.status_code == 401


@pytest.mark.parametrize("build", [_build_streamable_http_app, _build_sse_app])
def test_ohne_api_key_startet_keiner_der_http_transporte(monkeypatch, build):
    monkeypatch.delenv("MCP_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="MCP_API_KEY"):
        build()


def test_sse_nimmt_einen_oeffentlichen_host_an(monkeypatch):
    """Ohne `host=` setzt das SDK `127.0.0.1` voraus und schaltet damit still
    einen DNS-Rebinding-Schutz mit Localhost-Liste ein. Gemessen am 2026-09-27:
    jede Anfrage unter einem oeffentlichen Hostnamen kam mit HTTP 421
    «Invalid Host header» zurueck — also jede, die einen Container im Betrieb
    erreicht. Hier eine unbekannte Sitzung: die erwartete Absage ist 404,
    nicht 421."""
    monkeypatch.setenv("MCP_API_KEY", API_KEY)
    with TestClient(_build_sse_app(), base_url=PUBLIC_HOST) as c:
        r = c.post(
            "/messages/?session_id=" + "0" * 32,
            headers={"authorization": f"Bearer {API_KEY}"},
            json={},
        )
    assert r.status_code != 421, r.text
    assert r.status_code == 404
