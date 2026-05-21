## Finding: SEC-023 — Kein Rate-Limit auf MCP-Server-Ebene

**Severity:** high
**Status:** open
**Server:** register-mcp
**Check-Reference:** SEC-023
**PDF-Reference:** Hauptkatalog Sec 4 / Anhang B7 (Rate-Limit & Quota)

### Observed Behavior
Keine Rate-Limit-Middleware, kein `slowapi`, kein In-Memory-Counter, kein
Gateway-Pattern. `grep -rn "rate_limit\|RateLimit\|slowapi\|limiter" src/` liefert nichts.

Die Zefix-API hat selbst Rate-Limits (HTTP 429 wird in `_handle_http_error` abgefangen,
`src/register_mcp/server.py:101-102`), aber der MCP-Server reicht jeden Client-Call
1:1 durch.

### Expected Behavior
Bei Cloud-Deployment MUSS der Server Eigenschutz gegen exzessive Tool-Calls bieten:
- Per-Client/IP Rate-Limit (z.B. 60 req/min)
- Globaler Circuit-Breaker bei sustained 429 vom Upstream
- Quota-Tracking, damit ein einzelner LLM-Loop nicht die ganze Zefix-Quota verbrennt

### Evidence
- `src/register_mcp/server.py:101-102` — nur HTTP-429-Error-Handling, kein präventives Limiting
- Kein Middleware-Stack vor `mcp.run()`
- Pro Tool-Call: zusätzlicher `_fetch_legal_forms()` (n+1-Pattern) — verschärft Last

### Risk Description
1. Ein LLM-Agent in einer Endlosschleife kann den Server (und damit Zefix) lahmlegen
2. Cloud-Kosten skalieren ungebremst mit Bad Actors
3. Zefix kann den Server bei sustained Abuse blocken — alle anderen Nutzer leiden mit
4. Zusätzlich: `_fetch_legal_forms()` wird in jedem Search-Call neu geholt
   (`server.py:425, 506, 606, 724, 824`) — sollte gecacht werden (eigenes Finding ARCH)

### Remediation
**Quick-Win:**
```python
from collections import defaultdict
from time import monotonic

_call_log = defaultdict(list)

def _check_rate(client_id: str, limit: int = 60, window: int = 60) -> bool:
    now = monotonic()
    _call_log[client_id] = [t for t in _call_log[client_id] if now - t < window]
    if len(_call_log[client_id]) >= limit:
        return False
    _call_log[client_id].append(now)
    return True
```

Plus `@lru_cache` (oder TTL-Cache) auf `_fetch_legal_forms()` — die Liste ändert sich
selten und wird in jedem Tool-Call gebraucht.

**Robust:** `slowapi` oder Gateway davor (Cloudflare, Railway-eigene Limits).

### Effort Estimate
S (1d) für In-Memory-Limit + Legal-Forms-Cache; M für Gateway-Integration
