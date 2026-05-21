# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
