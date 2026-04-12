> 🇨🇭 **Part of the [Swiss Public Data MCP Portfolio](https://github.com/malkreide)**

# 🏛️ register-mcp

![Version](https://img.shields.io/badge/version-0.1.0-blue)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-Model%20Context%20Protocol-purple)](https://modelcontextprotocol.io/)
[![No Auth Required](https://img.shields.io/badge/auth-none%20required-brightgreen)](https://github.com/malkreide/register-mcp)
![CI](https://github.com/malkreide/register-mcp/actions/workflows/ci.yml/badge.svg)

> MCP Server for the Swiss Federal Commercial Register (Zefix/Handelsregister) and supporting reference data

[🇩🇪 Deutsche Version](README.de.md)

---

## Overview

`register-mcp` provides AI-native access to the Swiss Federal Commercial Register via the Zefix REST API, all without authentication:

| Source | Data | API |
|--------|------|-----|
| **Zefix (Handelsregister)** | Swiss companies, legal forms, SHAB mutations | ZefixREST v1 |
| **SHAB** | Official Gazette of Commerce — mutation publications | Embedded in Zefix |

Designed for Swiss public administration use cases: vendor verification, contract partner due diligence, procurement screening, and supplier onboarding — all via natural language queries.

**Anchor demo query:** *"We want to sign a framework agreement with Lehrmittelverlag Zürich AG. Is the company active in the commercial register, what is its stated corporate purpose, and have there been any SHAB mutations in the past two years?"*

---

## Features

- 🏛️ **6 tools** for company search, verification, and reference data
- 🔍 **`zefix_verify_company`** — quick active/dissolved status check
- 🌐 **Bilingual output** (Markdown / JSON)
- 🔓 **No API key required** — open data from zefix.admin.ch
- ☁️ **Dual transport** — stdio (Claude Desktop) + SSE (cloud)

---

## Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

---

## Installation

```bash
# Clone the repository
git clone https://github.com/malkreide/register-mcp.git
cd register-mcp

# Install
pip install -e .
# or with uv:
uv pip install -e .
```

Or with `uvx` (no permanent installation):

```bash
uvx register-mcp
```

---

## Quickstart

```bash
# stdio (for Claude Desktop)
python -m register_mcp.server

# SSE (cloud deployment)
MCP_TRANSPORT=sse PORT=8000 python -m register_mcp.server
```

Try it immediately in Claude Desktop:

> *"Is Lehrmittelverlag Zürich AG active in the commercial register?"*
> *"Look up the company with UID CHE-108.954.978"*
> *"List all Swiss legal forms"*

---

## Configuration

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "register": {
      "command": "python",
      "args": ["-m", "register_mcp.server"]
    }
  }
}
```

Or with `uvx`:

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

**Config file locations:**
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

### Cloud Deployment (SSE for browser access)

For use via **claude.ai in the browser** (e.g. on managed workstations without local software):

**Render.com (recommended):**
1. Push/fork the repository to GitHub
2. On [render.com](https://render.com): New Web Service → connect GitHub repo
3. Set start command: `python -m register_mcp.server --http --port 8000`
4. In claude.ai under Settings → MCP Servers, add: `https://your-app.onrender.com/sse`

> 💡 *"stdio for the developer laptop, SSE for the browser."*

---

## Available Tools

| Tool | Description |
|------|-------------|
| `zefix_search_companies` | Search companies by name, canton, legal form |
| `zefix_get_company` | Full company profile by internal EHRAID |
| `zefix_get_company_by_uid` | Company lookup by UID (CHE-xxx.xxx.xxx) |
| `zefix_verify_company` | Quick active/dissolved status check |
| `zefix_list_legal_forms` | All Swiss legal forms with IDs |
| `zefix_list_municipalities` | Swiss municipalities with BFS IDs |

### Example Use Cases

| Query | Tool |
|-------|------|
| *"Is Lehrmittelverlag Zürich AG active?"* | `zefix_verify_company` |
| *"Look up CHE-108.954.978"* | `zefix_get_company_by_uid` |
| *"Find companies named Migros in canton ZH"* | `zefix_search_companies` |
| *"List all Swiss legal forms"* | `zefix_list_legal_forms` |
| *"Show municipalities in canton Bern"* | `zefix_list_municipalities` |

---

## Architecture

```
┌─────────────────┐     ┌──────────────────────────────┐     ┌──────────────────────────┐
│   Claude / AI   │────▶│       register-mcp            │────▶│  Zefix (Handelsregister)  │
│   (MCP Host)    │◀────│       (MCP Server)            │◀────│  ZefixREST/api/v1        │
└─────────────────┘     │                              │     └──────────────────────────┘
                        │  6 Tools                     │
                        │  Stdio | SSE                 │
                        │  No authentication required  │
                        └──────────────────────────────┘
```

### Data Source Characteristics

| Source | Protocol | Coverage | Auth |
|--------|----------|----------|------|
| Zefix (Phase 1) | REST/JSON | Swiss companies, legal forms, SHAB | None |
| ZefixPublicREST (Phase 2) | REST/JSON | Signatories, capital, full history | Basic Auth (free) |
| UID Register (Phase 3) | SOAP | MwSt, NOGA codes, cross-validation | Public (20 req/min) |

---

## Phased Implementation

| Phase | API | Auth | Status |
|-------|-----|------|--------|
| **Phase 1** | `ZefixREST/api/v1` | None | **Current** |
| **Phase 2** | `ZefixPublicREST/api/v1` | Basic Auth (free, email zefix@bj.admin.ch) | Planned |
| **Phase 3** | UID-Register SOAP | Public (20 req/min) | Planned |

Phase 2 will add: signatory details, share capital, full historical entries.
Phase 3 will add: MwSt status, NOGA industry codes, cross-register validation.

---

## Project Structure

```
register-mcp/
├── src/register_mcp/
│   ├── __init__.py              # Package
│   └── server.py                # 6 tools (Zefix + reference data)
├── tests/
│   └── test_server.py           # Unit + integration tests (mocked HTTP)
├── docs/demo/
│   ├── demo.tape                # vhs recording script → demo.gif
│   ├── demo.py                  # Standalone CLI demo (live Zefix API)
│   └── README.md                # How to generate the demo GIF
├── .github/workflows/ci.yml     # GitHub Actions (Python 3.11/3.12/3.13)
├── pyproject.toml
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
├── README.md                    # This file (English)
└── README.de.md                 # German version
```

---

## Known Limitations

- Search by canton without a name filter may return API errors (Zefix API limitation)
- SHAB publication message text contains XML-style markup (`<FT TYPE="F">...`)
- Phase 1 API may be rate-limited under heavy load; retry after a short delay
- ZefixPublicREST (new API) requires registration: email zefix@bj.admin.ch

---

## Safety & Limits

### Rate Limits

| API | Limit | Notes |
|-----|-------|-------|
| ZefixREST (Phase 1) | Not officially documented | Throttling possible under heavy load — retry after 1–2 s |
| ZefixPublicREST (Phase 2) | Not officially documented | Requires prior registration (free) |
| UID-Register SOAP (Phase 3) | **20 req/min** | Hard limit, publicly documented |

### Data Privacy

- **Read-only access** — all tools carry `readOnlyHint: True`; the server performs no write, delete, or mutation operations against any API
- **No data storage** — the server acts as a stateless proxy; no company data is persisted, cached, or logged beyond the current request
- **Public register data only** — the Zefix Handelsregister is a public federal register (HRegV); data returned is legally public information, not personal data in the sense of DSG/GDPR
- **No personal tracking** — the server does not transmit user identity, query history, or session data to zefix.admin.ch

### Terms of Service & Data Sources

- **Zefix API ToS:** Usage of the Zefix REST API is governed by the [zefix.admin.ch terms of use](https://www.zefix.admin.ch). The data is published under the [Open Government Data (OGD) Switzerland](https://opendata.swiss/) principles.
- **SHAB:** Swiss Official Gazette of Commerce — published by the Federal Chancellery (BK). Public by law.
- **Institutional use:** This server is designed for read-only queries in public administration workflows. Not suitable for mass harvesting or automated surveillance use cases.

### Security

- No credentials are stored or transmitted (Phase 1)
- Phase 2 credentials (`ZEFIX_USER`, `ZEFIX_PASSWORD`) are passed via environment variables only — never hardcoded
- All HTTP calls use HTTPS exclusively
- Tool inputs are validated via Pydantic v2 before any API call is made

---

## Demo

> 📽️ *Demo GIF coming soon — see [`docs/demo/`](docs/demo/) to generate it locally with [vhs](https://github.com/charmbracelet/vhs)*

**Example interaction:**

```
User:  "Is Lehrmittelverlag Zürich AG active in the commercial register?"

→ Tool: zefix_verify_company(name="Lehrmittelverlag Zürich AG")

Claude: ✅ Lehrmittelverlag Zürich AG is ACTIVE in the Handelsregister.
        UID: CHE-109.741.634 | Canton: ZH | Legal form: AG
        Last SHAB mutation: 2024-06-15
```

To generate the demo GIF locally:

```bash
# Install vhs (macOS/Linux)
brew install vhs        # macOS
# or: go install github.com/charmbracelet/vhs@latest

# Generate
vhs docs/demo/demo.tape
# → outputs docs/demo/demo.gif
```

---

## Testing

```bash
# Unit tests (no API key required)
PYTHONPATH=src pytest tests/ -m "not live"

# Integration tests (live API calls)
pytest tests/ -m "live"
```

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md)

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md)

---

## License

MIT License — see [LICENSE](LICENSE)

---

## Author

Hayal Oezkan · [malkreide](https://github.com/malkreide)

---

## Credits & Related Projects

- **Zefix:** [zefix.admin.ch](https://www.zefix.admin.ch/) — Swiss Federal Commercial Register (BJ/FOJ)
- **SHAB:** Swiss Official Gazette of Commerce — mutation publications
- **Protocol:** [Model Context Protocol](https://modelcontextprotocol.io/) — Anthropic / Linux Foundation
- **Related:** [fedlex-mcp](https://github.com/malkreide/fedlex-mcp) — Commercial register ordinance (HRegV)
- **Related:** [zurich-opendata-mcp](https://github.com/malkreide/zurich-opendata-mcp) — Company seat + geodata
- **Related:** [swiss-statistics-mcp](https://github.com/malkreide/swiss-statistics-mcp) — Industry statistics by NOGA
- **Related:** [swiss-snb-mcp](https://github.com/malkreide/swiss-snb-mcp) — Economic indicators
- **Portfolio:** [Swiss Public Data MCP Portfolio](https://github.com/malkreide)
