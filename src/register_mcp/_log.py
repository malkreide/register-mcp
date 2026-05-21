"""Structured JSON logging for register-mcp."""

from __future__ import annotations

import functools
import json
import logging
import os
import sys
import time
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger("register_mcp")


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extras = getattr(record, "extra_fields", None)
        if isinstance(extras, dict):
            payload.update(extras)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    """Configure the register_mcp logger once. Idempotent."""
    if logger.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
    logger.propagate = False


def log_event(level: int, msg: str, **fields: Any) -> None:
    logger.log(level, msg, extra={"extra_fields": fields})


def logged_tool(tool_name: str) -> Callable[[Callable[..., Awaitable[str]]], Callable[..., Awaitable[str]]]:
    """Decorator: emits a single INFO event per tool call with latency + status."""

    def wrap(fn: Callable[..., Awaitable[str]]) -> Callable[..., Awaitable[str]]:
        @functools.wraps(fn)
        async def inner(params: Any) -> str:
            start = time.monotonic()
            status = "ok"
            try:
                return await fn(params)
            except Exception:
                status = "error"
                raise
            finally:
                log_event(
                    logging.INFO,
                    "tool_call",
                    tool=tool_name,
                    status=status,
                    latency_ms=int((time.monotonic() - start) * 1000),
                )

        return inner

    return wrap
