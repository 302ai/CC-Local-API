from __future__ import annotations

from typing import Any

from loguru import logger

from app.core.request_id_middleware import request_id_ctx


def _format_prefix(request_id: str) -> str:
    return f"[RequestID:{request_id}] " if request_id else ""


def log(level: str, message: str, **kwargs: Any) -> None:
    """Log with current request id injected.

    Usage:
        from app.core.log import log
        log("info", "hello", user_id=123)
    """

    request_id = request_id_ctx.get() or ""
    bound = logger.bind(request_id=request_id, **kwargs)
    bound.log(level.upper(), _format_prefix(request_id) + message)


def log_info(message: str, **kwargs: Any) -> None:
    log("info", message, **kwargs)


def log_warning(message: str, **kwargs: Any) -> None:
    log("warning", message, **kwargs)


def log_error(message: str, **kwargs: Any) -> None:
    log("error", message, **kwargs)
