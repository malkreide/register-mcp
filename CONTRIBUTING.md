# Contributing to register-mcp

Thank you for your interest in contributing to register-mcp!

## Quick Start

```bash
git clone https://github.com/malkreide/register-mcp
cd register-mcp
pip install -e ".[dev]"
pytest -m "not live" -v
```

## Guidelines

- **No-Auth-First:** Phase 1 tools must work without any API key or credentials.
- **Read-only:** All tools carry `readOnlyHint: True`. No write operations.
- **Pydantic v2:** Use `model_config`, `field_validator`, `model_dump()`.
- **Bilingual docs:** Update both `README.md` (EN) and `README.de.md` (DE).
- **Tests:** Add unit tests using `respx` mocks. Live tests use `@pytest.mark.live`.
- **Error messages:** In German (target audience: Swiss public administration).

## Adding a New Tool

1. Define a Pydantic `BaseModel` for inputs with `Field()` descriptions
2. Implement with `@mcp.tool(name="...", annotations={...})` decorator
3. Add unit test with `respx` mock
4. Add live test with `@pytest.mark.live`
5. Document in both READMEs

## Phase 2 (ZefixPublicREST)

To work on Phase 2, request API credentials: email `zefix@bj.admin.ch` with your name,
organisation, and intended use. Add credentials via environment variables:
`ZEFIX_USER` and `ZEFIX_PASSWORD`.

## Questions

Open an issue or discussion on GitHub.
