from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.response import ok
from app.core.command_runner import CommandRunner
from app.core.log import log_info

router = APIRouter()


@router.get("/health")
async def health():
    runner = CommandRunner()
    oc_health_check = await runner.exec_json("openclaw health --json")
    if oc_health_check.exit_code == 0:
        return ok({"status": "ok", "oc_status": "ok"})
    return ok({"status": "ok", "oc_status": "failed"})


@router.post("/webhook")
async def webhook(request: Request):
    payload = await request.body()
    log_info(f"webhook payload(raw): {payload!r}")
    try:
        json_payload = await request.json()
        log_info("webhook payload(json)", payload=json_payload)
    except Exception as e:
        log_info(f"webhook payload(json) parse failed: {e}")

    return ok()

