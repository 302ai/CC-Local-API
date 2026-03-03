from __future__ import annotations

import json
from typing import Any, Optional


from fastapi.responses import JSONResponse


def ok(payload: Any = None, *, status_code: int = 200) -> JSONResponse:
    if payload is None:
        return JSONResponse(status_code=status_code, content={"success": True})
    if isinstance(payload, dict):
        return JSONResponse(status_code=status_code, content={"success": True, **payload})
    return JSONResponse(status_code=status_code, content={"success": True, "data": payload})


def fail(
    message: str,
    *,
    status_code: int = 400,
    code: Optional[str] = None,
    payload: Optional[dict[str, Any]] = None,
) -> JSONResponse:
    out: dict[str, Any] = {"success": False, "error": {"message": message}}
    if code is not None:
        out["error"]["code"] = code
    if payload:
        out.update(payload)
    return JSONResponse(status_code=status_code, content=out)


import time


def gpt_stream_error_chunk(message: str) -> list[dict]:
    """返回两个 chunk：内容 + 结束标记"""
    base = {
        "id": "chatcmpl-error",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": "openclaw",
    }

    # chunk 1: 发送错误消息内容
    content_chunk = {
        **base,
        "choices": [
            {
                "index": 0,
                "delta": {"content": message},
                "finish_reason": None,  # ← 内容chunk应为null
            }
        ],
    }

    # chunk 2: 结束标记
    stop_chunk = {
        **base,
        "choices": [
            {
                "index": 0,
                "delta": {},  # ← 结束chunk的delta为空
                "finish_reason": "stop",
            }
        ],
    }

    return [content_chunk, stop_chunk]

async def oc_fail_stream(message: str):
    chunks = gpt_stream_error_chunk(message)
    for chunk in chunks:
        yield f"data: {json.dumps(chunk)}\n\n"
    yield "data: [DONE]\n\n"  # ← 别忘了这个结束标记！