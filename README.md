# register-mcp

> **Swiss Public Data MCP Portfolio** — Part of the [malkreide/swiss-public-data-mcp](https://github.com/malkreide) collection

[![PyPI](https://img.shields.io/pypi/v/register-mcp)](https://pypi.org/project/register-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/register-mcp)](https://pypi.org/project/register-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/malkreide/register-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/malkreide/register-mcp/actions)

MCP server providing read-only access to the **Swiss Federal Commercial Register (Zefix/Handelsregister)** and supporting reference data.

Designed for Swiss public administration use cases: vendor verification, contract partner due diligence, procurement screening, and supplier onboarding — all via natural language queries.

---

## Tools

| Tool | Description |
|------|-------------|
| `zefix_search_companies` | Search companies by name, canton, legal form |
| `zefix_get_company` | Full company profile by internal EHRAID |
| `zefix_get_company_by_uid` | Company lookup by UID (CHE-xxx.xxx.xxx) |
| `zefix_verify_company` | Quick active/dissolved status check |
| `zefix_list_legal_forms` | All Swiss legal forms with IDs |
| `zefix_list_municipalities` | Swiss municipalities with BFS IDs |

---

## Anchor Demo Query

> *«We want to sign a framework agreement with Lehrmittelverlag Zürich AG. Is the company active in the commercial register, what is its stated corporate purpose, and have there been any SHAB mutations in the past two years?»*

Claude calls `zefix_verify_company` → `zefix_get_company_by_uid` and returns a complete due diligence response in seconds — replacing manual searches on zefix.admin.ch.

---

## Architecture

```
┌─────────────────────────────────────┐
│           MCP Host (Claude)          │
│  zefix_search_companies              │
│  zefix_verify_company                │
│  zefix_get_company_by_uid            │
└──────────────┬──────────────────────┘
               │ JSON-RPC 2.0
               ▼
┌─────────────────────────────────────┐
│          register-mcp               │
│  FastMCP · httpx · Pydantic v2      │
│  Transport: stdio (local)           │
│             SSE (cloud/Railway)     │
└──────────────┬──────────────────────┘
               │ HTTPS
               ▼
┌─────────────────────────────────────┐
│  zefix.admin.ch/ZefixREST/api/v1    │
│  Swiss Federal Commercial Register  │
│  (Open API, no authentication)      │
└─────────────────────────────────────┘
```

---

## Phased Implementation

| Phase | API | Auth | Status |
|-------|-----|------|--------|
| **Phase 1** | `ZefixREST/api/v1` | None ✅ | **Current** |
| **Phase 2** | `ZefixPublicREST/api/v1` | Basic Auth (free, email zefix@bj.admin.ch) | Planned |
| **Phase 3** | UID-Register SOAP | Public (20 req/min) | Planned |

Phase 2 will add: signatory details, share capital, full historical entries.  
Phase 3 will add: MwSt status, NOGA industry codes, cross-register validation.

---

## Installation

### Claude Desktop (stdio)

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "register": {
      "command": "uvx",
      "args": ["register-mcp"]
    }
  }
}
```

### Cloud / Railway (SSE)

```bash
MCP_TRANSPORT=sse PORT=8000 uvx register-mcp
```

---

## Data Sources

- **Zefix (Handelsregister):** [zefix.admin.ch](https://www.zefix.admin.ch) — Swiss Federal Commercial Register, operated by the Federal Office of Justice (FOJ/BJ). Open data, no authentication required for Phase 1 endpoints.
- **SHAB:** Swiss Official Gazette of Commerce — mutation publications embedded in Zefix firm records.

---

## Known Limitations

- Search by canton without a name filter may return API errors (Zefix API limitation)
- SHAB publication message text contains XML-style markup (`<FT TYPE="F">...`)
- Phase 1 API may be rate-limited under heavy load; retry after a short delay
- ZefixPublicREST (new API) requires registration: email zefix@bj.admin.ch

---

## Portfolio Synergies

```
register-mcp ←→ zurich-opendata-mcp    company seat ↔ geodata
register-mcp ←→ fedlex-mcp            commercial register ordinance (HRegV)
register-mcp ←→ swiss-statistics-mcp  industry statistics by NOGA
register-mcp ←→ swiss-snb-mcp         economic indicators
```

---

## Development

```bash
git clone https://github.com/malkreide/register-mcp
cd register-mcp
pip install -e ".[dev]"
pytest -m "not live" -v          # unit tests (no API access)
pytest -m live -v                # live API tests
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). All contributions welcome.

---

## License

MIT — see [LICENSE](LICENSE).

---

*Part of the [Swiss Public Data MCP Portfolio](https://github.com/malkreide) — connecting AI models to Swiss public data sources.*
