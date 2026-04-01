# register-mcp

> **Swiss Public Data MCP Portfolio** — Teil der [malkreide/swiss-public-data-mcp](https://github.com/malkreide) Sammlung

[![PyPI](https://img.shields.io/pypi/v/register-mcp)](https://pypi.org/project/register-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/register-mcp)](https://pypi.org/project/register-mcp/)
[![Lizenz: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/malkreide/register-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/malkreide/register-mcp/actions)

MCP-Server für schreibgeschützten Zugriff auf das **Schweizer Handelsregister (Zefix)** und ergänzende Referenzdaten.

Entwickelt für den Einsatz in der öffentlichen Verwaltung: Lieferantenprüfung, Vertragspartner-Due-Diligence, Beschaffungs-Screening und Lieferanten-Onboarding — alles via natürlichsprachliche Abfragen.

---

## Tools

| Tool | Beschreibung |
|------|--------------|
| `zefix_search_companies` | Firmen nach Name, Kanton, Rechtsform suchen |
| `zefix_get_company` | Vollständiges Firmenprofil per EHRAID |
| `zefix_get_company_by_uid` | Firmendetails per UID (CHE-xxx.xxx.xxx) |
| `zefix_verify_company` | Schnell-Check: aktiv oder gelöscht? |
| `zefix_list_legal_forms` | Alle Schweizer Rechtsformen mit IDs |
| `zefix_list_municipalities` | Schweizer Gemeinden mit BFS-IDs |

---

## Anker-Demo-Query

> *«Wir möchten mit dem Lehrmittelverlag Zürich AG einen Rahmenvertrag abschliessen. Ist die Firma im Handelsregister aktiv eingetragen, welchen Gesellschaftszweck hat sie, und gab es in den letzten zwei Jahren SHAB-Mutationen?»*

Claude ruft `zefix_verify_company` → `zefix_get_company_by_uid` auf und liefert in Sekunden eine vollständige Due-Diligence-Antwort — statt manueller Suche auf zefix.admin.ch.

---

## Architektur

```
┌─────────────────────────────────────┐
│        MCP-Host (Claude)             │
│  zefix_search_companies              │
│  zefix_verify_company                │
│  zefix_get_company_by_uid            │
└──────────────┬──────────────────────┘
               │ JSON-RPC 2.0
               ▼
┌─────────────────────────────────────┐
│          register-mcp               │
│  FastMCP · httpx · Pydantic v2      │
│  Transport: stdio (lokal)           │
│             SSE (Cloud/Railway)     │
└──────────────┬──────────────────────┘
               │ HTTPS
               ▼
┌─────────────────────────────────────┐
│  zefix.admin.ch/ZefixREST/api/v1    │
│  Eidg. Handelsregister (EHRA)       │
│  (Offene API, keine Authentisierung) │
└─────────────────────────────────────┘
```

---

## Phasen-Roadmap

| Phase | API | Auth | Status |
|-------|-----|------|--------|
| **Phase 1** | `ZefixREST/api/v1` | Keine ✅ | **Aktuell** |
| **Phase 2** | `ZefixPublicREST/api/v1` | Basic Auth (kostenlos, zefix@bj.admin.ch) | Geplant |
| **Phase 3** | UID-Register SOAP | Öffentlich (20 Req/min) | Geplant |

Phase 2 ergänzt: Zeichnungsberechtigte, Stammkapital, vollständige Mutationshistorie.  
Phase 3 ergänzt: MWST-Status, NOGA-Branchencodes, registerübergreifende Validierung.

---

## Installation

### Claude Desktop (stdio)

In `claude_desktop_config.json` eintragen:

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

## Datenquellen

- **Zefix (Handelsregister):** [zefix.admin.ch](https://www.zefix.admin.ch) — Zentrales Firmenindex-Register, betrieben vom Bundesamt für Justiz (BJ). Phase-1-Endpunkte: offen, keine Authentisierung erforderlich.
- **SHAB:** Schweizerisches Handelsamtsblatt — Mutationspublikationen eingebettet in Zefix-Firmendaten.

---

## Bekannte Einschränkungen

- Suche nach Kanton ohne Namensfilter kann zu API-Fehlern führen (Zefix-Limitation)
- SHAB-Publikationstexte enthalten XML-Markup (`<FT TYPE="F">...`)
- Phase-1-API kann bei hoher Last gedrosselt werden; kurz warten und erneut versuchen
- ZefixPublicREST (neue API) erfordert Registrierung: E-Mail an zefix@bj.admin.ch

---

## Portfolio-Synergien

```
register-mcp ←→ zurich-opendata-mcp    Firmensitz ↔ Geodaten
register-mcp ←→ fedlex-mcp            Handelsregisterverordnung (HRegV)
register-mcp ←→ swiss-statistics-mcp  Branchenstatistiken per NOGA
register-mcp ←→ swiss-snb-mcp         Wirtschaftsindikatoren
```

---

## Entwicklung

```bash
git clone https://github.com/malkreide/register-mcp
cd register-mcp
pip install -e ".[dev]"
pytest -m "not live" -v          # Unit-Tests (kein API-Zugriff)
pytest -m live -v                # Live-API-Tests
```

---

## Mitwirken

Siehe [CONTRIBUTING.md](CONTRIBUTING.md). Beiträge sind willkommen.

---

## Lizenz

MIT — siehe [LICENSE](LICENSE).

---

*Teil des [Swiss Public Data MCP Portfolio](https://github.com/malkreide) — KI-Modelle mit Schweizer öffentlichen Datenquellen verbinden.*
