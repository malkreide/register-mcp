# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Defence-in-depth (Sprint 3 of mcp-audit-skill remediation):**
  - Egress allow-list: `_make_client` registers an httpx request hook
    that rejects any outbound URL whose host is not in `ALLOWED_HOSTS`
    (default `{www.zefix.admin.ch}`; override via `MCP_ALLOWED_HOSTS`).
    Fires on the initial request and on every redirect, so a malicious
    `Location` header cannot exfiltrate. Closes `SEC-021`.
  - Optional OpenTelemetry tracing behind `OTEL_EXPORTER_OTLP_ENDPOINT`,
    activated by the `[otel]` extra. No-op without env var or deps.
  - 6 new tests in `tests/test_egress.py` (allowed pass, evil host blocked,
    AWS-IMDS blocked, redirect-to-evil blocked, case normalisation).

### Added
- **Supply-chain & container hardening (Sprint 2 of mcp-audit-skill remediation):**
  - `Dockerfile` (multi-stage, `python:3.13-slim`, non-root `mcp` user,
    `uv sync --frozen --no-dev` from `uv.lock`); closes audit finding `SEC-007`.
  - `compose.yaml` for local dev with `read_only`, `cap_drop: ALL`,
    `no-new-privileges`.
  - `uv.lock` committed for reproducible builds.
  - `.github/dependabot.yml` with weekly pip + docker, monthly actions updates.
  - `SECURITY.md` with disclosure pathway and response SLAs.
  - `.github/CODEOWNERS` requiring review on security-sensitive surfaces.
  - CI extended: `lockfile` job runs `uv lock --locked`; `docker` job builds
    the image and smoke-tests (must fail without `MCP_API_KEY`, must run as
    user `mcp`). Together these close audit finding `OPS-Supply-Chain`.

### Added
- **SSE transport hardening (Sprint 1 of mcp-audit-skill remediation):**
  - Bearer-token authentication via `MCP_API_KEY` env var — server refuses to
    start in SSE mode without it (closes audit finding `SEC-AUTH-SSE`).
  - In-memory sliding-window rate limit (`MCP_RATE_LIMIT` / `MCP_RATE_WINDOW`,
    defaults 60/60s) per bearer-token hash; returns HTTP 429 with
    `Retry-After` (closes `SEC-023`).
  - Structured JSON logging on stderr for every tool call with `tool`, `status`,
    `latency_ms`; auth-failures and rate-limit events at WARNING (closes `OBS-001`).
  - TTL cache (24h, `LEGAL_FORMS_TTL`) on Zefix `legalForm` reference data
    (closes `ARCH-CACHE`).
- 11 new tests under `tests/test_security.py` covering auth, rate-limit, cache.

### Changed
- `register-mcp` console script now points at `register_mcp.server:main` instead
  of `mcp.run` directly, so the SSE entry-point can install middleware.

## [0.1.0] - 2026-04-01

### Added
- Initial release with Phase 1 implementation (no authentication required)
- **Zefix tools**: `zefix_search_companies`, `zefix_get_company`, `zefix_get_company_by_uid`, `zefix_verify_company`
- **Reference data**: `zefix_list_legal_forms`, `zefix_list_municipalities`
- Dual transport: stdio (Claude Desktop) + SSE (cloud/Railway)
- GitHub Actions CI (Python 3.11, 3.12, 3.13)
- Bilingual documentation (DE/EN)
- Unit and integration tests (mocked HTTP via respx)
