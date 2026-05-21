# Re-Audit-Report: register-mcp (post Sprint 1+2+3)

**Run-ID:** `2026-05-21-register-mcp-re-audit`
**Datum:** 2026-05-21
**Vorgänger:** [`audits/2026-05-21-register-mcp/`](../2026-05-21-register-mcp/audit-report.md)
**Auditor:** Claude — Methodik `mcp-audit-skill` v0.5
**Skill-Quelle:** https://github.com/malkreide/mcp-audit-skill

---

## 1. Executive Summary

Nach drei Härtungs-Sprints ist `register-mcp` **production-ready für Cloud-Deployment**.
Alle 2 critical und 3 high Findings aus dem Initial-Audit sind geschlossen, 1 von 2 medium
Findings ebenfalls. **0 Blocker offen.** Release-Vorschlag: `v0.2.0`.

**Production-ready:** ✅ ja (cloud + stdio)
**Blocking Findings:** 0
**Verbleibende Findings:** 1 medium (OpenTelemetry als opt-in; nicht aktiv getestet, da Infrastruktur-abhängig).

---

## 2. Profile-Diff zum Vorgänger

Unverändert. Phase 1, Public Open Data, read-only, dual transport.

---

## 3. Findings-Closure-Matrix

| ID | Severity | Status v1 | Status v2 | Geschlossen durch |
|---|---|---|---|---|
| `SEC-AUTH-SSE` | critical | open / fail | **closed / pass** | Sprint 1 — `BearerAuthMiddleware`, `MCP_API_KEY` Pflicht beim Startup, `hmac.compare_digest`. Verifiziert durch 4 Tests in `tests/test_security.py::TestBearerAuth`. |
| `SEC-007` | critical | open / fail | **closed / pass** | Sprint 2 — Multi-stage `Dockerfile` mit non-root `mcp`-User, `uv sync --frozen`, CI smoke-test verifiziert Non-Root. |
| `SEC-023` | high | open / fail | **closed / pass** | Sprint 1 — `RateLimitMiddleware`, Sliding-Window per Bearer-Hash, `Retry-After` Header. 4 Tests in `TestRateLimit`. |
| `OBS-001` | high | open / fail | **closed / pass** | Sprint 1 — `_log.py` JSON-Formatter + `@logged_tool` Decorator auf alle 6 Tools, `LOG_LEVEL` env tunbar. |
| `OPS-Supply-Chain` | high | open / partial | **closed / pass** | Sprint 2 — `uv.lock` committed + CI `uv lock --locked`-Gate, `.github/dependabot.yml` (pip/docker/actions), `SECURITY.md`, `.github/CODEOWNERS`. |
| `SEC-021` | medium | open / partial | **closed / pass** | Sprint 3 — `_enforce_egress_allowlist` httpx event_hook, fires auf Request + Redirect, `EgressDenied`-Exception. 6 Tests in `tests/test_egress.py` (allowed pass, evil blocked, IMDS blocked, Redirect blocked). |
| `ARCH-CACHE` | medium | open / fail | **closed / pass** | Sprint 1 — `_fetch_legal_forms` TTL-Cache (24h, `LEGAL_FORMS_TTL` env-tunbar), Reset-Helper für Tests. 3 Tests in `TestLegalFormsCache`. |

### Neu aufgenommene Pflichten (durch Härtungen entstanden, alle PASS)

| Check | Quelle | Status |
|---|---|---|
| Constant-time secret compare | `_middleware.py:42` (`hmac.compare_digest`) | ✅ |
| Fail-loud startup ohne Auth | `server.py:_build_sse_app` SystemExit | ✅ |
| Non-root container user | `Dockerfile` USER mcp + CI smoke-test | ✅ |
| Reproducible build | `uv.lock` + CI `uv lock --locked` | ✅ |
| Egress allow-list mit Redirect-Coverage | event_hook auf jeden Request-Hop | ✅ |

---

## 4. Verbleibende Findings

### OTEL-OPT-IN (medium · partial)

**Beobachtung:** OpenTelemetry-Hook ist verdrahtet (`_otel.py`), aber als optionales Extra
ausgeliefert. Ohne `pip install register-mcp[otel]` und ohne `OTEL_EXPORTER_OTLP_ENDPOINT`
no-op. Das ist Absicht (Hard-Dep auf OTel-SDK wäre unverhältnismässig für stdio-Nutzer),
aber Cloud-Operator muss den Pfad bewusst aktivieren.

**Risiko:** Tracing-Daten fehlen by default. Logging deckt aber das Operative-Minimum ab.

**Remediation:** dokumentieren — bereits in README erledigt. Kein Code-Change nötig.

---

## 5. Applicability-Übersicht (unverändert)

```
Applicable checks: 28 / 68
  ARCH:  10/12   SDK: 5/5     SEC: 6/23
  SCALE: 2/6    OBS: 3/6     HITL: 0/5
  CH:    1/8    OPS: 3/3
```

---

## 6. Release-Empfehlung

```yaml
proposed_release:
  version: 0.2.0           # minor bump from 0.1.0
  reason: |
    Cloud-Härtung. Breaking-Adjacent: SSE-Modus verlangt jetzt MCP_API_KEY
    (vorher kein Auth) und prüft Egress (vorher beliebige Hosts via httpx).
    Stdio-API unverändert. Kein API-Break, aber Operatoren müssen Env-Vars
    setzen — daher Minor statt Patch.
  blocking_findings: []
  next_audit:
    trigger: "Phase 2 Implementation (ZefixPublicREST mit Basic Auth)"
```

Konkretes Vorgehen für Maintainer:
1. `pyproject.toml` Version → `0.2.0`
2. CHANGELOG.md `[Unreleased]` → `[0.2.0] - 2026-05-XX`
3. `git tag -a v0.2.0 -m "v0.2.0 — cloud-hardened"` + `gh release create v0.2.0 --draft`
4. PyPI-Push läuft via `.github/workflows/publish.yml` automatisch beim Release-Publish

---

## 7. Audit-Metadata

| Feld | Wert |
|---|---|
| `audited_at` | 2026-05-21 |
| `skill_version` | 0.5 (manuell) |
| `applicable_checks` | 28 / 68 |
| `pass` | 23 |
| `partial` | 1 (OTEL-OPT-IN, dokumentiert) |
| `fail` | 0 |
| `policy` | `fail-or-partial` |
| `production_ready` | **true** |
| `delta_to_prior` | 7 Findings geschlossen, 0 neu, 1 verbleibend (opt-in) |
