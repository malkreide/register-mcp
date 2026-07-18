> 🇨🇭 **Part of the [Swiss Public Data MCP Portfolio](https://github.com/malkreide)**

# 🏛️ register-mcp

![Version](https://img.shields.io/badge/version-0.3.0-blue)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-Model%20Context%20Protocol-purple)](https://modelcontextprotocol.io/)
[![No Auth Required](https://img.shields.io/badge/auth-none%20required-brightgreen)](https://github.com/malkreide/register-mcp)
![CI](https://github.com/malkreide/register-mcp/actions/workflows/ci.yml/badge.svg)

> MCP Server for the Swiss Federal Commercial Register (Zefix/Handelsregister) and the official gazettes portal (SHAB + cantonal Amtsblätter), joined on the UID

[🇩🇪 Deutsche Version](README.de.md)

---

## Overview

`register-mcp` provides AI-native access to **two** Swiss federal data sources, joined on the UID, all without authentication:

| Source | Data | API |
|--------|------|-----|
| **Zefix (Handelsregister)** | Swiss companies, legal forms, registered-office data | ZefixREST v1 |
| **Amtsblattportal** | SHAB **and** cantonal gazettes — 2.79M publications (HR mutations, calls to creditors, procurement, bankruptcies, …) | amtsblattportal.ch v1 |

The two sources share one key — the **UID**. The value is in the join: **Zefix tells you whether a company exists; the gazette tells you what it does.**

Designed for Swiss public administration use cases: vendor verification, contract partner due diligence, procurement screening, and supplier onboarding — all via natural language queries.

**Anchor demo query:** *"We want to sign a framework agreement with Lehrmittelverlag Zürich AG. Is the company active in the commercial register, what is its stated corporate purpose, what SHAB mutations were there in the past two years — and has it appeared in any procurement (Submissions) publications?"*

That single question walks the whole tool chain across both sources:

```
zefix_search_company  →  zefix_verify_company  →  gazette_company_publications(uid=…)  →  gazette_get_publication(id=…)
```

---

## Features

- 🏛️ **11 tools** across two sources — company search & verification (Zefix) + gazette publications (SHAB/cantonal)
- 🔗 **`gazette_company_publications`** — the UID join: everything published about a company
- 🔍 **`zefix_verify_company`** — quick active/dissolved status check
- 🌐 **Bilingual output** (Markdown / JSON) with per-source attribution + `provenance`
- 🔓 **No API key required** — open data from zefix.admin.ch and amtsblattportal.ch
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

# SSE (cloud deployment) — MCP_API_KEY is REQUIRED
MCP_API_KEY=$(openssl rand -hex 32) MCP_TRANSPORT=sse PORT=8000 \
  python -m register_mcp.server
```

### SSE / Cloud Deployment

When running with `MCP_TRANSPORT=sse`, the server enforces:

- **Bearer-token auth** — set `MCP_API_KEY` to a secret string. Clients must send
  `Authorization: Bearer <key>` on every request. Missing or wrong → HTTP 401.
  The server refuses to start without `MCP_API_KEY` set.
- **Rate limiting** — sliding window per bearer-token hash. Defaults: 60 req / 60 s.
  Tunable via `MCP_RATE_LIMIT` and `MCP_RATE_WINDOW`. Exceeding the limit returns
  HTTP 429 with `Retry-After`.
- **Structured JSON logging** — every tool call emits one line to stderr with
  `tool`, `status`, `latency_ms`. Auth failures and rate-limit events are logged
  at WARNING level. Configure verbosity with `LOG_LEVEL` (default `INFO`).
- **Reference-data cache** — Zefix legal-forms are cached for 24h
  (`LEGAL_FORMS_TTL` seconds) to avoid an extra upstream call per tool invocation.
- **Egress allow-list** — outbound HTTP is restricted to `www.zefix.admin.ch`
  and `amtsblattportal.ch` via an `httpx` request hook that also fires on
  redirects. A `Location` header pointing elsewhere raises `EgressDenied` and is
  never followed. Override with `MCP_ALLOWED_HOSTS=host1,host2` (comma-separated,
  lower-case).

  > ⚠️ **Upgrade note (0.2.x → 0.3.0):** `amtsblattportal.ch` was added to the
  > **default** allow-list when the gazette tools shipped. If your deployment
  > **pins** `MCP_ALLOWED_HOSTS`, that value overrides the default entirely —
  > add `amtsblattportal.ch` to it, or every `gazette_*` call will raise
  > `EgressDenied`.
- **Optional OpenTelemetry tracing** — install with `pip install register-mcp[otel]`
  and set `OTEL_EXPORTER_OTLP_ENDPOINT` (e.g. `http://otel-collector:4318/v1/traces`).
  Without the extra or without the env var the server stays silent — no hard
  dependency on the OTel SDK.

For multi-instance deployments, place a real gateway (Cloudflare, Railway internal
networking, an API-Gateway with Redis-backed rate limiting) in front of the
in-memory limiter, which is per-process by design.

### Container deployment

A minimal multi-stage `Dockerfile` ships with the repo. The image runs as a
non-root `mcp` user; dependencies are resolved from `uv.lock` (`uv sync
--frozen`), so the build is reproducible.

```bash
docker build -t register-mcp:local .

docker run --rm -p 8000:8000 \
  -e MCP_TRANSPORT=sse \
  -e MCP_API_KEY="$(openssl rand -hex 32)" \
  register-mcp:local
```

For local iteration there is a `compose.yaml` with `read_only`, `cap_drop: ALL`
and `no-new-privileges`:

```bash
MCP_API_KEY=$(openssl rand -hex 32) docker compose up --build
```

See [SECURITY.md](SECURITY.md) for hardening notes (egress restriction, key
rotation, SIEM forwarding).

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

**Zefix — commercial register (6):**

| Tool | Description |
|------|-------------|
| `zefix_search_companies` | Search companies by name, canton, legal form |
| `zefix_get_company` | Full company profile by internal EHRAID |
| `zefix_get_company_by_uid` | Company lookup by UID (CHE-xxx.xxx.xxx) |
| `zefix_verify_company` | Quick active/dissolved status check |
| `zefix_list_legal_forms` | All Swiss legal forms with IDs |
| `zefix_list_municipalities` | Swiss municipalities with BFS IDs |

**Amtsblattportal — SHAB + cantonal gazettes (5):**

| Tool | Description |
|------|-------------|
| `gazette_company_publications` | **The UID join.** All gazette publications for a UID, newest first, optional rubric/time filters |
| `gazette_search_publications` | Full-text search (`keyword`) + `rubrics`/`subRubrics`/`cantons`/date-range filters |
| `gazette_get_publication` | Single publication incl. XML full text, defensively parsed |
| `gazette_list_rubrics` | Rubric/subRubric taxonomy — prerequisite for valid filters |
| `gazette_source_status` | Reachability of both sources + cache ages (rubrics, legal forms) |

The prefix is `gazette_`, not `shab_`, because the source covers SHAB **and** the cantonal gazettes.

### Example Use Cases

| Query | Tool |
|-------|------|
| *"Is Lehrmittelverlag Zürich AG active?"* | `zefix_verify_company` |
| *"Look up CHE-108.954.978"* | `zefix_get_company_by_uid` |
| *"Find companies named Migros in canton ZH"* | `zefix_search_companies` |
| *"What has been published about CHE-116.115.052?"* | `gazette_company_publications` |
| *"Find gazette publications mentioning 'Schulhaus' in canton ZH"* | `gazette_search_publications` |
| *"Which procurement (SB) sub-rubrics exist?"* | `gazette_list_rubrics` |

---

## Architecture

```
                                                          ┌──────────────────────────────┐
                                                    ┌────▶│  Zefix (Handelsregister)     │
                                                    │     │  www.zefix.admin.ch          │
┌─────────────────┐     ┌──────────────────────────┴─┐   │  ZefixREST/api/v1            │
│   Claude / AI   │────▶│       register-mcp           │   └──────────────────────────────┘
│   (MCP Host)    │◀────│       (MCP Server)           │   ┌──────────────────────────────┐
└─────────────────┘     │  11 Tools (zefix_ + gazette_)├──▶│  Amtsblattportal             │
                        │  Stdio | SSE                 │   │  amtsblattportal.ch/api/v1   │
                        │  Egress allow-list           │   │  SHAB + cantonal gazettes    │
                        │  No authentication required  │   └──────────────────────────────┘
                        └──────────────────────────────┘
                              join key: UID (CHE-XXX.XXX.XXX)
```

### Data Source Characteristics

| Source | Protocol | Coverage | Auth |
|--------|----------|----------|------|
| Zefix | REST/JSON | Swiss companies, legal forms, registered offices | None |
| Amtsblattportal | REST/JSON (list) + XML (full text) | SHAB + cantonal gazettes, 2.79M publications | None |
| ZefixPublicREST (planned) | REST/JSON | Signatories, capital, full history | Basic Auth (free) |
| UID Register (planned) | SOAP | MwSt, NOGA codes, cross-validation | Public (20 req/min) |

---

## Architecture decision

**ARCH A — live-API-only**, consistent with the existing Zefix integration
(decided 2026-07-18).

The Amtsblattportal is queried live on every call. All endpoints respond in
0.2–2.0 s, and the use case — targeted company and topic research — does not
need a local bulk copy. A bulk dump would mean mirroring 2.79M records, with an
ongoing sync burden and staleness risk, for no benefit to the join-on-UID
workflow. The taxonomy (`/rubrics`) and the Zefix legal-forms list are the only
data cached, each for 24h in memory, because they change at most a few times a
year and every filtered call needs them.

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
│   └── server.py                # 11 tools (Zefix + gazette)
├── tests/
│   ├── test_server.py           # Zefix unit + integration tests (mocked HTTP)
│   ├── test_gazette.py          # Gazette tools + the three quirks (mocked HTTP)
│   └── test_egress.py           # Egress allow-list
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
- Phase 1 Zefix API may be rate-limited under heavy load; retry after a short delay
- ZefixPublicREST (new API) requires registration: email zefix@bj.admin.ch

### Amtsblattportal — verified behaviour (live-checked 2026-07-18)

| Call | HTTP | Status | Records | Note |
|---|---|---|---|---|
| `/publications?publicationStates=PUBLISHED` | 200 | OK | 2,790,323 | baseline (full corpus) |
| `?uids=CHE-116.115.052` | 200 | **OK** | 4 | **the join — core feature** |
| `?keyword=Lehrmittelverlag` | 200 | OK | 34 | full-text search |
| `?keyword=Schulhaus&cantons=ZH` | 200 | OK | 157 | filters combine |
| `?rubrics=SB` | 200 | OK | 22,511 | procurement / Submissionen |
| `?subRubrics=HR01` | 200 | OK | 398,036 | usable without `rubrics` |
| `?publicationDate.start=…&.end=…` | 200 | OK | 28,482 | date-range filter |
| `/publications/{id}/xml` | 200 | OK | – | full text, rubric-specific schema |
| `/rubrics` | 200 | OK | – | full rubric/subRubric taxonomy |
| `?rubrics=ZZZZ` (invalid) | **200** | **Silent Empty** | 0, `total: null` | Quirk 2 |
| `?uid=…` (wrong param name) | **200** | **Silent Ignore** | **2,790,323** | Quirk 1 |
| `?text=Schule` (wrong param name) | **200** | **Silent Ignore** | **2,790,323** | Quirk 1 |

**Three quirks are defended in code** (details in the [CHANGELOG](CHANGELOG.md)
under *Known findings*):

- **Quirk 1 — Silent Ignore (critical).** Unknown query parameters are dropped
  silently and return the full 2.79M corpus with HTTP 200. Defence: query
  strings are built exclusively from an `ALLOWED_GAZETTE_PARAMS` allow-list, and
  every filtered response is plausibility-checked — a `total` above 2,000,000 is
  rejected as *"filter ignored by upstream — result not trustworthy"*.
- **Quirk 2 — Silent Empty.** An invalid rubric code returns HTTP 200 with an
  empty result. Defence: the `/rubrics` taxonomy is cached 24h and every code is
  validated **before** any call, failing with the five closest valid codes.
- **Quirk 3 — Two-step fetch.** The JSON list carries only `meta`; the content
  lives only in the per-rubric namespaced XML. Defence: namespace-agnostic
  defensive parsing (`meta` + `publicationText` mandatory, HR `company` when
  present, everything else in `additional_fields`).

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

![register-mcp demo](assets/demo.png)

> 📽️ *Terminal GIF coming soon — see [`docs/demo/`](docs/demo/) to generate it locally with [vhs](https://github.com/charmbracelet/vhs)*

**Example interaction:**

```
User:  "Is Lehrmittelverlag Zürich AG active in the commercial register?"

→ Tool: zefix_verify_company(name="Lehrmittelverlag Zürich AG")

Claude: ✅ Lehrmittelverlag Zürich AG is ACTIVE in the Handelsregister.
        UID: CHE-109.741.634 | Canton: ZH | Legal form: AG
        Last SHAB mutation: 2024-06-15
```

[→ More use cases by audience →](EXAMPLES.md)

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
- **Amtsblattportal:** [amtsblattportal.ch](https://amtsblattportal.ch/) — SHAB and cantonal gazettes (SECO / Swiss Confederation)
- **Protocol:** [Model Context Protocol](https://modelcontextprotocol.io/) — Anthropic / Linux Foundation
- **Related:** [fedlex-mcp](https://github.com/malkreide/fedlex-mcp) — Commercial register ordinance (HRegV)
- **Related:** [zurich-opendata-mcp](https://github.com/malkreide/zurich-opendata-mcp) — Company seat + geodata
- **Related:** [swiss-statistics-mcp](https://github.com/malkreide/swiss-statistics-mcp) — Industry statistics by NOGA
- **Related:** [swiss-snb-mcp](https://github.com/malkreide/swiss-snb-mcp) — Economic indicators
- **Portfolio:** [Swiss Public Data MCP Portfolio](https://github.com/malkreide)

<!-- mcp-name: io.github.malkreide/register-mcp -->

<!-- BEGIN GENERATED: install -->
## Installation

Run via [`uv`](https://docs.astral.sh/uv/)'s `uvx` — no clone or manual install needed. Add to your MCP client config (`mcpServers` for Claude Desktop, Cursor and Windsurf; use a top-level `servers` key for VS Code in `.vscode/mcp.json`):

```json
{
  "mcpServers": {
    "register-mcp": {
      "command": "uvx",
      "args": [
        "register-mcp"
      ]
    }
  }
}
```
<!-- END GENERATED: install -->
