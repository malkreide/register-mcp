## Finding: ARCH-CACHE — Reference-Daten werden bei jedem Tool-Call neu geladen

**Severity:** medium
**Status:** open
**Server:** register-mcp
**Check-Reference:** ARCH (Performance / Caching)
**PDF-Reference:** Hauptkatalog Sec 2 (Tool-Design Efficiency)

### Observed Behavior
`_fetch_legal_forms()` (`src/register_mcp/server.py:363-368`) wird in 5 von 6 Tools
bei jedem Aufruf erneut ausgeführt:
- `server.py:425` (`zefix_search_companies`)
- `server.py:506` (`zefix_get_company`)
- `server.py:606` (`zefix_get_company_by_uid`)
- `server.py:724` (`zefix_verify_company`)
- `server.py:824` (`zefix_list_legal_forms`)

Die Rechtsformen-Liste ändert sich realistisch ≤ 1× pro Jahr.

### Expected Behavior
Statische / langsam-veränderliche Reference-Daten gehören in einen TTL-Cache
(z.B. 24h), damit der Server nicht für jede Firmen-Suche zwei API-Calls macht.

### Evidence
Bei einem typischen User-Flow (Suche → Verifikation → Detail) entstehen so 3
zusätzliche Calls auf `legalForm`, obwohl 1 reichen würde. Bei 1000 Calls/Tag
sind das 3000 statt 1000 Upstream-Hits.

### Risk Description
- Verschärft das Rate-Limit-Problem (SEC-023)
- Erhöht Latenz für den User um ~200ms pro Tool-Call
- Macht den Server fragiler gegen Zefix-Outages (zwei API-Punkte statt einer pro Call)

### Remediation
```python
from functools import lru_cache
from time import monotonic

_legal_forms_cache: tuple[float, list[dict]] | None = None

async def _fetch_legal_forms(ttl: float = 86400) -> list[dict]:
    global _legal_forms_cache
    now = monotonic()
    if _legal_forms_cache and now - _legal_forms_cache[0] < ttl:
        return _legal_forms_cache[1]
    async with _make_client() as client:
        r = await client.get(f"{ZEFIX_BASE}/legalForm")
        r.raise_for_status()
        data = r.json()
    _legal_forms_cache = (now, data)
    return data
```

### Effort Estimate
S (< 1d)
