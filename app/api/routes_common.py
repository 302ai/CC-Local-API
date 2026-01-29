from __future__ import annotations

from fastapi import APIRouter

from app.api.response import fail, ok


router = APIRouter()


@router.get("/health")
def health():
    return ok({"status": "ok"})

