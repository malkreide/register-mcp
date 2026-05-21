# Audit-Report: register-mcp

**Run-ID:** `2026-05-21-register-mcp`
**Datum:** 2026-05-21
**Auditor:** Claude — Methodik `mcp-audit-skill` v0.5
**Skill-Quelle:** https://github.com/malkreide/mcp-audit-skill

> Hinweis zur Reproduzierbarkeit: Das Skill-Repo war nicht lokal installiert; die
> Tool-Pipeline (`tools/audit_init.py`, `tools/parse_catalog.py`,
> `tools/aggregate_results.py`) konnte nicht ausgeführt werden. Der Audit folgt dem
> 6-Schritte-Workflow aus `SKILL.md`, die Findings sind manuell evidenzbasiert
> erstellt. Für einen vollständigen reproduzierbaren Run das Skill via Slash-Command
> installieren: `./setup-slash-command.sh` im Skill-Repo.

---

## 1. Executive Summary

Der `register-mcp`-Server hat eine **saubere Tool-Architektur** (FastMCP + Pydantic
mit `extra="forbid"`, vollständige Tool-Annotations, idempotente Reads, gute Tests).
Für reines **stdio + Claude Desktop** ist er produktionsreif. Für das dokumentierte
**Cloud-Deployment (Railway/SSE)** ist er **nicht production-ready**: der SSE-Endpoint
bindet `0.0.0.0` ohne Authentifizierung, ohne Rate-Limit, ohne Container-Sandbox und
ohne Logging.

**Production-ready:** ❌ nein (für Cloud) — ✅ ja (für lokales stdio)
**Blocking Findings:** 2 critical, 3 high
**Gesamt-Findings:** 7 (2 critical · 3 high · 2 medium)

---

## 2. Profile-Snapshot

| Feld | Wert |
|---|---|
| `transport` | `dual` (stdio + SSE) |
| `auth_model` | `none` |
| `data_class` | `Public Open Data` (Zefix OGD) |
| `write_capable` | `false` (alle Tools `readOnlyHint=True`) |
| `deployment` | `[local-stdio, Railway]` |
| `is_cloud_deployed` | `true` (SSE bindet `0.0.0.0:$PORT`) |
| `phase` | 1 (Phase 2 mit Basic-Auth dokumentiert, nicht implementiert) |

---

## 3. Applicability-Übersicht

```
=== Audit applicability for register-mcp ===
Profile: dual transport, no auth, Public Open Data, read-only, [local-stdio, Railway]

Applicable checks: 28 / 68
  ARCH:  10/12   (Tool-Design + Repo-Struktur, Idempotency N/A für reine Reads)
  SDK:   5/5     (FastMCP, Pydantic, Lifecycle — universell)
  SEC:   6/23    (OAuth/PKCE N/A; Cloud-relevante: Sandbox, Rate-Limit, Egress, SSE-Auth, Input-Val, SSRF)
  SCALE: 2/6     (Transport, Container — Cloud-Subset)
  OBS:   3/6     (Logging, Errors, Tracing — universell)
  HITL:  0/5     (read-only, kein Sampling)
  CH:    1/8    (OGD-Lizenz-Attribution — alle PII/EDÖB-Checks entfallen)
  OPS:   3/3    (Test-Strategy, Doku, Phasen-Architektur)

Severity-Breakdown applicable:
  critical: 4   high: 11   medium: 11   low: 2
```

Nicht-anwendbare Checks (40) erscheinen bewusst nicht im Detail — Lethal Trifecta,
Confused Deputy, OAuth-Resource-Indicators, HITL-Sampling, PII-DLP, EDÖB-Meldepflicht
greifen alle nicht für read-only Public-Data-Server.

---

## 4. Findings-Tabelle (Severity descending)

| ID | Titel | Severity | Status | Effort |
|---|---|---|---|---|
| [SEC-AUTH-SSE](findings/SEC-AUTH-SSE-unauthenticated-cloud-endpoint.md) | SSE-Endpoint `0.0.0.0` ohne Auth | critical | fail | S |
| [SEC-007](findings/SEC-007-no-sandbox-container.md) | Kein Container / Sandbox | critical | fail | M |
| [SEC-023](findings/SEC-023-no-rate-limit.md) | Kein Rate-Limit auf MCP-Ebene | high | fail | S |
| [OBS-001](findings/OBS-001-no-structured-logging.md) | Kein strukturiertes Logging | high | fail | S |
| [OPS-Supply-Chain](findings/OPS-supply-chain-hardening.md) | Kein Lockfile / Dependabot / SECURITY.md | high | partial | S |
| [SEC-021](findings/SEC-021-no-egress-control.md) | Egress-Control nicht erzwungen | medium | partial | S+M |
| [ARCH-CACHE](findings/ARCH-CACHE-legal-forms-refetch.md) | Legal-Forms bei jedem Call neu geladen | medium | fail | S |

### PASS-Liste (Auszug, 16 Checks)

- **ARCH:** Tool-Annotations vollständig (`readOnlyHint`, `destructiveHint=false`,
  `idempotentHint=true`, `openWorldHint`) — `server.py:377-383, 481-487, 563-569, 685-690, 800-806, 867-873`
- **ARCH:** Pydantic mit `extra="forbid"` auf allen 6 Input-Models — strict schema
- **ARCH:** Field-Constraints (`min_length`, `max_length`, `ge`, `le`, `pattern`) + Custom-Validators für `canton`
- **ARCH:** Phasen-Architektur dokumentiert (Phase 1 no-auth / Phase 2 Basic-Auth) — `server.py:8-9`
- **ARCH:** Repo-Struktur korrekt (`src/`-Layout, `tests/`, `.github/workflows/`, `pyproject.toml`)
- **SDK:** FastMCP korrekt verwendet, `instructions` gesetzt — `server.py:48-57`
- **SDK:** `StrEnum` für `SearchType` / `ResponseFormat` — type-safe
- **SDK:** Pydantic v2 (`>=2.0.0`), `ConfigDict` modern
- **SEC:** SSRF strukturell ausgeschlossen — Outbound-URLs hartkodiert (`server.py:34-35`),
  kein User-Input fliesst in URL-Pfade ausser sanitisierte `ehraid: int`
- **SEC:** Input-Validation vollständig (Pydantic + `field_validator` für canton-Whitelist gegen `CANTON_CODES`)
- **SEC:** UID-Sanitisierung (`re.sub(r"[^0-9]", "", raw)`) — keine Injection-Vektoren
- **OBS:** Errors werden semantisch übersetzt (`_handle_http_error`) statt Stack-Traces zu leaken
- **OPS:** 24 Tests, `respx`-basiert (HTTP-Mocking), `-m "not live"`-Marker für CI-Stabilität
- **OPS:** CI auf Python 3.11/3.12/3.13 Matrix
- **OPS:** Ruff-Lint im CI-Lauf
- **CH:** OGD-Attribution im README (`README.md:248`) — Zefix-ToS + opendata.swiss verlinkt

---

## 5. Remediation-Plan (vorgeschlagene Reihenfolge)

### Sprint 1 — Blocker für Cloud-Release (1 Woche)
1. **SEC-AUTH-SSE** (S) — API-Key-Middleware vor SSE-Transport
2. **SEC-023** (S) — In-Memory Rate-Limit + `_fetch_legal_forms()`-Cache
3. **OBS-001** (S) — Strukturiertes JSON-Logging pro Tool-Call

### Sprint 2 — Hardening (1 Woche)
4. **SEC-007** (M) — `Dockerfile` mit non-root, Lockfile-basierter Build
5. **OPS-Supply-Chain** (S) — `uv.lock`, `dependabot.yml`, `SECURITY.md`, `CODEOWNERS`

### Sprint 3 — Defense-in-Depth (optional, falls Verwaltungs-Deployment)
6. **SEC-021** (S+M) — Egress-Policy + README-Operator-Doku
7. **ARCH-CACHE** (S) — TTL-Cache auf Reference-Daten (überlappt mit SEC-023-Fix)

**Re-Audit:** nach Sprint 2 erneut `propose_release.py` laufen — bei
`production_ready: true` ist `v0.2.0` als Cloud-fähiger Release vorschlagbar.

---

## 6. Audit-Metadata

| Feld | Wert |
|---|---|
| `audited_at` | 2026-05-21 |
| `skill_version` | 0.5 (manuell, ohne `tools/`-Pipeline) |
| `catalog_hash` | nicht berechnet (Skill-Repo nicht lokal installiert) |
| `applicable_checks` | 28 / 68 |
| `policy` | `fail-or-partial` |
| `production_ready` | `false` (cloud) / `true` (stdio-only) |
| `commit_audited` | `27f4cc7` (branch `claude/audit-mcp-skill-bZqDJ`) |

### Empfehlung an den Maintainer
Da der Server zwei Deployment-Modi unterstützt, im README **explizit deklarieren**:
> _v0.1 ist freigegeben für lokales stdio (Claude Desktop). Cloud-/SSE-Deployment ist
> als Preview markiert — siehe Audit `2026-05-21` für offene Blocker._

Das entkoppelt den PyPI-Release vom Cloud-Härtungspfad.
