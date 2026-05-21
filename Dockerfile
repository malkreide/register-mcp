# syntax=docker/dockerfile:1.7
# Multi-stage build: install deps with uv, then ship a slim runtime image.
FROM python:3.14-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# uv pinned via its official image to avoid pulling a curl|sh install script.
# Pin to a specific patch — the short `:0.8` form is not published as a tag,
# so the previous `:0.5` reference failed to resolve in CI. Dependabot will
# bump this via the docker ecosystem hook in .github/dependabot.yml.
COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /uvx /usr/local/bin/

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/

# --frozen: refuse to update the lockfile; build fails loud if it drifted.
RUN uv sync --frozen --no-dev --no-editable

# ---------------------------------------------------------------------------

FROM python:3.14-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    MCP_TRANSPORT=sse \
    PORT=8000

RUN groupadd --system mcp && useradd --system --gid mcp --home-dir /app --shell /usr/sbin/nologin mcp

WORKDIR /app
COPY --from=builder --chown=mcp:mcp /app/.venv /app/.venv
COPY --chown=mcp:mcp src/ /app/src/

USER mcp
EXPOSE 8000

# MCP_API_KEY must be provided at runtime — the server fails loud if missing.
CMD ["python", "-m", "register_mcp.server"]
