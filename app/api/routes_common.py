from __future__ import annotations

from fastapi import APIRouter

from app.api.response import fail, ok
from app.core.command_runner import CommandRunner

router = APIRouter()


@router.get("/health")
async def health():
    runner = CommandRunner()
    oc_health_check = await runner.exec_json("openclaw health --json")
    if oc_health_check.exit_code == 0:
        return ok({"status": "ok"})
    return fail(oc_health_check.stderr, payload={"status": "fail"})

