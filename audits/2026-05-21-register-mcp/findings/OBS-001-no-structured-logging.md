## Finding: OBS-001 — Kein strukturiertes Logging

**Severity:** high
**Status:** open
**Server:** register-mcp
**Check-Reference:** OBS-001
**PDF-Reference:** Hauptkatalog Sec 6 / Anhang B10

### Observed Behavior
Kein einziger `import logging`, kein `structlog`, kein `getLogger()` im gesamten `src/`.
Errors werden als User-facing Strings via `_handle_http_error()` zurückgegeben
(`src/register_mcp/server.py:89-108`) — aber nirgends persistiert oder strukturiert
geloggt.

### Expected Behavior
MCP-Server in produktiver Nutzung müssen pro Tool-Call mindestens loggen:
- Tool-Name, Input-Hash (PII-frei), Status (ok/error), Latency
- Upstream-Status-Code, Retry-Count
- Strukturiert (JSON-Lines) für SIEM-Konsum

### Evidence
- `grep -rn "import logging\|getLogger\|structlog" src/` → 0 Treffer
- Errors werden silenced + als String returned, nicht escaliert
- Kein Audit-Trail für "wer hat wann welche Firma abgefragt"

### Risk Description
- **Operational:** Bei Bug-Reports «irgendwas hängt» fehlt jegliche Debug-Spur
- **Compliance:** Auch bei Public Open Data verlangt gute Governance einen Audit-Trail
  über Zugriffsmuster — speziell wenn der Server in Schweizer Verwaltung läuft
- **Security:** Kein Anomalie-Detection-Hook (z.B. 1000 UID-Lookups in 1min = scraping)

### Remediation
```python
import logging
import json
logger = logging.getLogger("register_mcp")

# in jedem Tool, am Ende:
logger.info(json.dumps({
    "tool": "zefix_search_companies",
    "name_len": len(params.name or ""),
    "canton": params.canton,
    "results": len(summaries),
    "status": "ok",
}))
```

Plus Konfiguration via `LOG_LEVEL`/`LOG_FORMAT` env vars.

### Effort Estimate
S (< 1d)
