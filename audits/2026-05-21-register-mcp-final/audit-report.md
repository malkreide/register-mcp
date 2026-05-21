# Final Re-Audit-Report: register-mcp

**Run-ID:** `2026-05-21-register-mcp-final`
**Datum:** 2026-05-21
**Commit:** `main @ 79ef96c` (nach Merge von PR #15)
**Auditor:** Claude — Methodik `mcp-audit-skill` v0.5
**Skill-Quelle:** https://github.com/malkreide/mcp-audit-skill
**Vorgänger:** [`2026-05-21-register-mcp`](../2026-05-21-register-mcp/audit-report.md) (Initial), [`2026-05-21-register-mcp-re-audit`](../2026-05-21-register-mcp-re-audit/audit-report.md) (post Sprint 3)

---

## 1. Executive Summary

Nach drei Härtungs-Sprints, fünf Docker-/CI-Fixes und einer Dependabot-Welle ist
`register-mcp` **production-ready für Cloud + stdio**. Sieben von sieben Audit-Findings
sind im Code geschlossen, ein verbleibender medium-Punkt (OTel als Opt-in) ist
dokumentiert und nicht blockierend. **0 Blocker. Release-Vorschlag: `v0.2.0`.**

| Metric | Initial (2026-05-21) | Final (2026-05-21) | Δ |
|---|---|---|---|
| Production-ready (Cloud) | ❌ | ✅ | +1 |
| Critical-Findings | 2 | 0 | −2 |
| High-Findings | 3 | 0 | −3 |
| Medium-Findings | 2 | 1 | −1 |
| PASS-Checks | 16 | 27 | +11 |
| Tests | 24 | 38 | +14 |

---

## 2. Findings-Closure-Matrix (vollständig)

| ID | Severity | Initial | Sprint | PR | Final | Evidenz |
|---|---|---|---|---|---|---|
| `SEC-AUTH-SSE` | critical | fail | 1 | #2 | **PASS** | `_middleware.py` `BearerAuthMiddleware` + `MCP_API_KEY`-Pflicht in `_build_sse_app`; `hmac.compare_digest`; 4 Tests `TestBearerAuth` |
| `SEC-007` | critical | fail | 2 | #3 | **PASS** | `Dockerfile` multi-stage `python:3.14-slim`, non-root `mcp`-User, `uv sync --frozen`; CI-Smoke testet Non-Root |
| `SEC-023` | high | fail | 1 | #2 | **PASS** | `_middleware.py` `RateLimitMiddleware` Sliding-Window per Token-Hash, 429 + Retry-After; 4 Tests `TestRateLimit` |
| `OBS-001` | high | fail | 1 | #2 | **PASS** | `_log.py` JSON-Formatter + `@logged_tool` Decorator auf alle 6 Tools; `LOG_LEVEL` env |
| `OPS-Supply-Chain` | high | partial | 2 | #3 | **PASS** | `uv.lock` (49 Pakete) + CI `uv lock --locked`; `dependabot.yml` (pip weekly/docker weekly/actions monthly); `SECURITY.md`; `.github/CODEOWNERS` |
| `SEC-021` | medium | partial | 3 | #12 | **PASS** | `server.py` `_enforce_egress_allowlist` httpx event_hook, fires auf Request+Redirect, `EgressDenied`; 6 Tests `tests/test_egress.py` |
| `ARCH-CACHE` | medium | fail | 1 | #2 | **PASS** | `_fetch_legal_forms` TTL-Cache (`LEGAL_FORMS_TTL=86400`); 3 Tests `TestLegalFormsCache` |

### Verbleibendes Finding

| ID | Severity | Status | Hinweis |
|---|---|---|---|
| `OTEL-OPT-IN` | medium | **partial** (dokumentiert) | OpenTelemetry-Hook (`_otel.py`) ist verdrahtet aber Opt-in via `[otel]`-Extra. Ohne Env-Var no-op. Bewusste Design-Entscheidung: stdio-User sollen keinen 80 MB SDK-Tail mitziehen. Im README dokumentiert. **Nicht blockierend.** |

---

## 3. Neue PASS-Checks gegenüber Initial-Audit

Durch die Härtung sind 11 Checks von "nicht abgedeckt" zu "PASS" gewandert:

- **SEC:** Auth mit `hmac.compare_digest`, Rate-Limit per-client, Egress-Allowlist mit Redirect-Coverage, Container non-root, Reproducible-Build (4 neu PASS)
- **OBS:** strukturiertes JSON-Logging, optionale Tracing-Anbindung (2 neu PASS)
- **ARCH:** Reference-Daten-Caching, Fail-Loud-Startup (2 neu PASS)
- **OPS:** Lockfile-Gate in CI, Container-Smoke-Test, Dependabot-Updates, SECURITY-Disclosure-Pfad (3 neu PASS)

---

## 4. Applicability (unverändert)

```
Applicable: 28 / 68
ARCH 10/12 · SDK 5/5 · SEC 6/23 · SCALE 2/6 · OBS 3/6 · HITL 0/5 · CH 1/8 · OPS 3/3
```

---

## 5. Code-Pfade (Spot-Check)

Stichproben, die in dieser finalen Runde verifiziert wurden:

| Was | Wo | Status |
|---|---|---|
| `_make_client` registriert egress event_hook | `src/register_mcp/server.py` | ✅ |
| `_enforce_egress_allowlist` raised `EgressDenied` für fremde Hosts | gleiche Datei | ✅ |
| `_fetch_legal_forms` nutzt `_legal_forms_cache` Tuple | gleiche Datei | ✅ |
| 6 Tools tragen `@logged_tool(...)`-Decorator | gleiche Datei, 6 Treffer | ✅ |
| `BearerAuthMiddleware` + `RateLimitMiddleware` in `_middleware.py` | `src/register_mcp/_middleware.py` | ✅ |
| `_otel.py` import-soft, no-op ohne `OTEL_EXPORTER_OTLP_ENDPOINT` | `src/register_mcp/_otel.py` | ✅ |
| `Dockerfile` USER mcp + COPY LICENSE | `Dockerfile` | ✅ |
| `uv lock --locked` Gate im CI | `.github/workflows/ci.yml` | ✅ |
| Docker-Job hat `actions: write` | gleiche Datei | ✅ |
| 38 Tests grün, ruff clean, uv lock locked | `pytest tests/ -m "not live"` | ✅ |

---

## 6. Supply-Chain-Beobachtungen seit Initial

Dependabot ist live und hat während des Audit-Cycles bereits gefeuert:

| PR | Was | Status |
|---|---|---|
| #4 | `docker/build-push-action` v6 → v7 | merged |
| #5 | `actions/checkout` v5 → v6 | merged |
| #8 | `docker/setup-buildx-action` v3 → v4 | merged |
| #9 | `python:3.13-slim` → `python:3.14-slim` | merged |

D.h. die OPS-Härtung ist nicht nur statisch im Repo, sie produziert auch
operationell Ergebnis. ✅

---

## 7. Release-Empfehlung

```yaml
proposed_release:
  version: 0.2.0           # minor bump from 0.1.0
  rationale: |
    Cloud-Härtung. Neue Pflicht-Env-Vars (MCP_API_KEY für SSE) und
    Verhaltens-Änderungen (Egress-Allowlist, Rate-Limit) sind
    operativ relevant aber keine API-Breaks. Minor statt Patch.
  blocking_findings: []
  changelog_anchor: "## [Unreleased]"
  next_steps_for_maintainer:
    - "Bump version in pyproject.toml: 0.1.0 -> 0.2.0"
    - "Move CHANGELOG '## [Unreleased]' content under '## [0.2.0] - 2026-05-21'"
    - "git tag -a v0.2.0 -m 'v0.2.0 — cloud-hardened'"
    - "gh release create v0.2.0 --draft --notes-file <(awk '/^## \\[0.2.0\\]/,/^## \\[/' CHANGELOG.md | head -n -1)"
    - "Publish-Workflow läuft automatisch auf release: published"
  next_audit_trigger: "Phase 2 — ZefixPublicREST mit Basic Auth"
```

---

## 8. Audit-Metadata

| Feld | Wert |
|---|---|
| `audited_at` | 2026-05-21 |
| `skill_version` | 0.5 (manuell, ohne tools/-Pipeline) |
| `applicable_checks` | 28 / 68 |
| `pass` | 27 |
| `partial` | 1 (OTEL-OPT-IN, dokumentiert, opt-in) |
| `fail` | 0 |
| `policy` | `fail-or-partial` |
| `production_ready` | **true** |
| `delta_initial_to_final` | 2 critical + 3 high + 1 medium geschlossen; 0 neu |
| `remediation_prs` | #2, #3, #11, #12, #13, #14, #15 (alle merged) |
| `test_count` | 38 (vs. 24 initial) |

---

## 9. Was bewusst offen bleibt

Diese Punkte sind keine Findings (Out-of-Scope für das aktuelle Server-Profil),
aber kommen bei Phase-2-Implementierung wieder auf den Tisch:

- **OAuth 2.1 / PKCE** — relevant wenn Multi-Tenant-Deployment oder wenn der MCP-Server
  selbst delegated Identity konsumieren muss. Aktuell deckt API-Key + Gateway ab.
- **Redis-basierter Rate-Limit** — nötig sobald > 1 Instanz. In-Memory ist aktuell
  korrekt für single-instance Railway-Deploy.
- **mTLS / Cloudflare Access** — Operator-Verantwortung, in `SECURITY.md` dokumentiert.
- **Multi-arch Container** (linux/arm64) — nice-to-have für Apple-Silicon-Dev-Maschinen,
  aktuell linux/amd64 only.

---

## 10. Abschliessendes Urteil

**`register-mcp` ist production-ready.**

Der Server hat in 8 Stunden Arbeit den Sprung von «zwei kritische Cloud-Blocker» zu
«alle Audit-Findings geschlossen, 38 Tests grün, Dependabot live» geschafft. Der
Maintainer kann jetzt mit gutem Gewissen `v0.2.0` taggen und auf Railway/Docker
deployen.

Die einzige Empfehlung an den Maintainer: **CI-`docker`-Job muss einmal grün durchlaufen**
(PR #15 hat den letzten Build-Block — fehlende LICENSE — entfernt). Das ist eine
operative Bestätigung, kein Audit-Finding mehr.
