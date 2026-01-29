from __future__ import annotations

from fastapi import HTTPException, Request


async def parse_request_data(request: Request) -> dict:
    """解析请求体，根据 Content-Type 支持 JSON 和 multipart/form-data。"""
    content_type = request.headers.get("Content-Type", "")

    if "application/json" in content_type:
        data = await request.json()
    elif "multipart/form-data" in content_type:
        form = await request.form()
        images = form.getlist("image") or []
        data = dict(form)
        data["image"] = images
    else:
        raise HTTPException(
            status_code=400,
            detail=f"不支持 {content_type} content_type 类型",
        )

    return data
