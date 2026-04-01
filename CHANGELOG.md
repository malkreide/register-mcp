# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-04-01

### Added
- Initial release with Phase 1 implementation (no authentication required)
- **Zefix tools**: `zefix_search_companies`, `zefix_get_company`, `zefix_get_company_by_uid`, `zefix_verify_company`
- **Reference data**: `zefix_list_legal_forms`, `zefix_list_municipalities`
- Dual transport: stdio (Claude Desktop) + SSE (cloud/Railway)
- GitHub Actions CI (Python 3.11, 3.12, 3.13)
- Bilingual documentation (DE/EN)
- Unit and integration tests (mocked HTTP via respx)
