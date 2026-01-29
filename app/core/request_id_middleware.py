from __future__ import annotations

import json
from contextvars import ContextVar

from fastapi import Request
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware

from app.utils.utils import get_uuid

REQUEST_ID_HEADER = "X-Request-ID"

# Holds request id for the current async context.
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


def truncate_long_strings(obj, max_length: int = 50):
    if isinstance(obj, str):
        if len(obj) > max_length:
            return obj[:max_length] + "...(truncated)"
        return obj
    elif isinstance(obj, dict):
        return {k: truncate_long_strings(v, max_length) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [truncate_long_strings(item, max_length) for item in obj]
    elif isinstance(obj, bytes):
        try:
            decoded = obj.decode("utf-8", errors="ignore")
            return truncate_long_strings(decoded, max_length)
        except Exception:
            return f"<bytes:{len(obj)}>"
    else:
        return obj


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = get_uuid(remove_hyphen=True)
        request.state.request_id = request_id
        request.state.upstream_request_id = ""
        token = request_id_ctx.set(request_id)

        # Streaming endpoints: don't read body.
        is_streaming = False
        stream_url_path = [
            "/302/claude-code/sandbox/file/download",
            "/302/claude-code/messages",
            "/302/claude-code/skills/detail",
            "/302/claude-code/chat/completions",
            "/302/claude-code/sandbox/execute/stream"
        ]
        if request.url.path in stream_url_path:
            is_streaming = True

        if is_streaming:
            logger.info(f"[RequestID:{request_id}] Request: {request.method} {request.url.path} [Streaming endpoint]")
        else:
            body = await request.body()
            body_str = body.decode("utf-8", errors="ignore") if body else ""
            short_body = self._process_request_body(request, body_str)

            query_params = dict(request.query_params) if request.query_params else {}
            query_str = f"Query: {truncate_long_strings(query_params)}" if query_params else ""

            logger.info(
                f"[RequestID:{request_id}] Request: {request.method} {request.url.path} {query_str} Body: {short_body}"
            )

            async def receive():
                return {"type": "http.request", "body": body}

            request._receive = receive

        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id

        upstream_request_id = getattr(request.state, "upstream_request_id", "")
        logger.info(f"[RequestID:{request_id}] upstream_request_id from state: '{upstream_request_id}'")

        if upstream_request_id:
            response.headers["Request-Id"] = upstream_request_id

        logger.info(f"[RequestID:{request_id}] Response: {response.status_code}")

        # For StreamingResponse, response body is produced after middleware returns.
        # Resetting the ContextVar here can raise in streaming scenarios because
        # the token may no longer belong to the current context.
        if getattr(response, "body_iterator", None) is not None:
            original_iterator = response.body_iterator

            async def _iter_with_ctx_reset():
                try:
                    async for chunk in original_iterator:
                        yield chunk
                finally:
                    request_id_ctx.reset(token)

            response.body_iterator = _iter_with_ctx_reset()
            return response

        request_id_ctx.reset(token)
        return response

    def _process_request_body(self, request: Request, body_str: str) -> str:
        if not body_str:
            return ""

        content_type = request.headers.get("content-type", "").lower()

        try:
            if "application/json" in content_type:
                json_body = json.loads(body_str)
                return str(truncate_long_strings(json_body))

            elif "application/x-www-form-urlencoded" in content_type:
                from urllib.parse import parse_qs

                parsed_data = parse_qs(body_str)
                form_keys = list(parsed_data.keys())
                if len(form_keys) > 5:
                    return f"Form data with {len(form_keys)} fields: {form_keys[:5]}...(truncated)"
                return f"Form data: {form_keys}"

            elif "multipart/form-data" in content_type:
                field_names = self._extract_multipart_fields(body_str)
                if "filename=" in body_str or any("image" in name.lower() for name in field_names):
                    return f"Multipart form with file upload, fields: {field_names}"
                return f"Multipart form data, fields: {field_names}"

            elif "text/" in content_type:
                return truncate_long_strings(body_str, 100)

            else:
                return f"Binary data ({len(body_str)} bytes)"

        except Exception as e:
            return f"Body parsing error: {str(e)[:50]}"

    def _extract_multipart_fields(self, body_str: str) -> list:
        try:
            import re

            return re.findall(r'name="([^"]+)"', body_str)
        except Exception:
            return []
