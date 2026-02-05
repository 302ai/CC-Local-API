from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.response import ok
from app.core.command_runner import CommandRunner

router = APIRouter()


class CommandRequest(BaseModel):
    command: str
    cwd: Optional[str] = None
    env: Optional[dict[str, str]] = None
    timeout: Optional[float] = 300


def sse_message(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {__import__('json').dumps(data, ensure_ascii=False)}\n\n"


@router.post("/commands")
async def execute_command(payload: CommandRequest):
    runner = CommandRunner()
    result = await runner.exec_json(
        payload.command,
        cwd=payload.cwd,
        env=payload.env,
        timeout=payload.timeout,
    )
    return ok(
        {
            "result": {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "error": result.error,
                "exit_code": result.exit_code,
            }
        }
    )


@router.post("/commands/stream")
async def execute_command_stream(payload: CommandRequest, request: Request):
    runner = CommandRunner()

    async def gen():
        run_id: Optional[str] = None
        try:
            async for ev in runner.stream(
                payload.command,
                cwd=payload.cwd,
                env=payload.env,
                timeout=payload.timeout,
            ):
                if ev.get("event") == "start":
                    run_id = ev.get("run_id")

                if await request.is_disconnected():
                    if run_id:
                        await runner.kill(run_id)
                    break

                event = ev.get("event")
                if event == "start":
                    yield sse_message(
                        "start",
                        {"run_id": ev["run_id"], "pid": ev["pid"], "command": ev["command"]},
                    )
                elif event == "output":
                    yield sse_message("output", {"run_id": ev["run_id"], "text": ev["text"]})
                elif event == "error":
                    yield sse_message("error", {"run_id": ev["run_id"], "error": ev.get("error")})
                elif event == "done":
                    yield sse_message(
                        "done",
                        {"run_id": ev["run_id"], "exit_code": ev.get("exit_code"), "lines": ev.get("lines")},
                    )
        finally:
            if run_id:
                await runner.cleanup(run_id)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )