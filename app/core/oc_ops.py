from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.command_runner import CommandRunner, CommandResult
from app.core.file_content import read_file_as_text_async
from app.core.http_client import fetch_json_with_retry


async def oc_new_session_and_list_active(
    *,
    oc_agent_id: str,
    runner: CommandRunner,
    active: int = 3,
    oc_config_path: Path = Path("/home/user/.openclaw/openclaw.json"),
    chat_completions_url: str = "http://127.0.0.1:18789/v1/chat/completions",
) -> tuple[Any, CommandResult]:
    """Create a new OpenClaw session (/new) and list active sessions.

    This function only performs OpenClaw operations and returns raw results.
    Callers can decide how to parse/persist the session info.
    """
    oc_config_json_str = await read_file_as_text_async(oc_config_path)
    oc_config = json.loads(oc_config_json_str)
    token = oc_config.get("gateway", {}).get("auth", {}).get("token")

    headers = {"Authorization": f"Bearer {token}", "x-openclaw-agent-id": oc_agent_id}
    new_session_payload = {
        "model": "openclaw",
        "messages": [{"role": "user", "content": "/new"}],
        "stream": False,
    }

    new_resp = await fetch_json_with_retry(
        "POST",
        chat_completions_url,
        headers=headers,
        json=new_session_payload,
    )

    list_sessions_result = await runner.exec_json(
        f"openclaw sessions --agent '{oc_agent_id}' --json --active {active}"
    )

    return new_resp, list_sessions_result