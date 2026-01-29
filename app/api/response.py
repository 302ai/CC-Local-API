from __future__ import annotations

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