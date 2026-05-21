## Finding: SEC-AUTH-SSE — Unauthenticated SSE Endpoint on 0.0.0.0

**Severity:** critical
**Status:** open
**Server:** register-mcp
**Check-Reference:** SEC-AUTH-SSE (analog Hauptkatalog Sec 4 / Anhang B5)
**PDF-Reference:** Anhang B5 (Auth & Authz für HTTP-Transport)

### Observed Behavior
In `src/register_mcp/server.py:63-66` wird bei `MCP_TRANSPORT=sse` der Server auf
`0.0.0.0:$PORT` gebunden — ohne jegliche Authentifizierung, Bearer-Token oder API-Key:

```python
transport = os.environ.get("MCP_TRANSPORT", "stdio")
if transport == "sse":
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = int(os.environ.get("PORT", "8000"))
```

`grep -rn "Authorization\|HTTPBearer\|api_key" src/` liefert nichts. Jeder, der den
Railway-/Cloud-Endpoint erreicht, kann alle 6 Tools aufrufen.

### Expected Behavior
Ein cloud-deployed MCP-Server MUSS gemäss MCP-Spec 2025-06-18 + Hauptkatalog Sec 4
mindestens einen der folgenden Schutzmechanismen vor dem SSE-Endpoint haben:
- OAuth 2.1 (PKCE) — Best Practice für Multi-Client-Szenarien
- Pre-shared API-Key via Header — Minimum für interne Deployments
- mTLS / Cloud-Provider-Auth-Gateway (z.B. Cloudflare Access)

### Evidence
- `src/register_mcp/server.py:63-66` — bind to 0.0.0.0 ohne Auth-Middleware
- README.md zeigt SSE-Deployment ohne Auth-Hinweis
- Keine `Authorization`-Header-Validierung im gesamten Codebase

### Risk Description
Auch wenn die Daten public sind (Zefix OGD), erzeugt ein offener Endpoint:
1. **Resource-Abuse:** unkontrollierte Zefix-API-Calls auf Kosten der eigenen Quota / Rate-Limits
2. **Reputations-Risiko:** der eigene Server wird zum Open Proxy für Zefix
3. **DoS-Vektor:** beliebige Clients können Loops triggern und Cloud-Kosten generieren
4. **Compliance:** EDÖB-Meldepflicht-Trigger sind zwar low (kein PII), aber ein offener
   Bundes-Datenendpoint wirft Governance-Fragen auf

### Remediation
**Option A (Minimum, S):** API-Key-Middleware vor SSE:
```python
if transport == "sse":
    expected_key = os.environ["MCP_API_KEY"]  # fail-loud wenn nicht gesetzt
    @mcp.middleware
    async def require_api_key(req, call_next):
        if req.headers.get("authorization") != f"Bearer {expected_key}":
            return Response(status_code=401)
        return await call_next(req)
```

**Option B (Empfohlen, M):** Cloudflare Access / Railway-Internal-Networking vor den
Endpoint schalten und im README dokumentieren, dass der MCP-Server **nicht** direkt
ans Internet darf.

**Option C (Strategisch, L):** OAuth 2.1 + PKCE implementieren — passt aber erst bei
Phase 2 mit ZefixPublicREST (Basic Auth aus eigenem Setup), wo schon Credentials im
Spiel sind.

### Effort Estimate
S (Option A) — < 1d, primär Middleware + Doku
