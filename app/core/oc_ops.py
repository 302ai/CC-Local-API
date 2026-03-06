from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiohttp
from asgiref.timeout import timeout

from app.core.command_runner import CommandRunner, CommandResult
from app.core.file_content import read_file_as_text_async
from app.core.http_client import fetch_json_with_retry, fetch_sse_with_retry
from app.core.log import log_info


def _oc_extract_agent_name_from_session_key(oc_session_key: str) -> str | None:
    # Expected format: agent:<agentName>:<provider>:<uuid>
    # Example: agent:testoc:openai:90f8496d-3041-4312-93ad-61721b2e32ce
    parts = oc_session_key.split(":")
    if len(parts) >= 4 and parts[0] == "agent" and parts[1]:
        return parts[1]
    return None


async def _oc_read_session_provider_model(
    *,
    oc_session_key: str,
    oc_agent_name: str,
    base_dir: Path = Path("/home/user/.openclaw/agents"),
) -> tuple[str | None, str | None]:
    sessions_path = base_dir / oc_agent_name / "sessions" / "sessions.json"
    try:
        sessions_json_str = await read_file_as_text_async(sessions_path)
        sessions = json.loads(sessions_json_str)
    except Exception:
        return None, None

    if not isinstance(sessions, dict):
        return None, None

    entry = sessions.get(oc_session_key)
    if not isinstance(entry, dict):
        return None, None

    provider = entry.get("modelProvider")
    model = entry.get("model")
    return (
        provider if isinstance(provider, str) else None,
        model if isinstance(model, str) else None,
    )


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
        timeout=aiohttp.ClientTimeout(total=None, sock_read=120, connect=10)
    )

    list_sessions_result = await runner.exec_json(
        f"openclaw sessions --agent '{oc_agent_id}' --json --active {active}"
    )

    return new_resp, list_sessions_result


async def oc_has_model_in_openclaw_config(
    *,
    oc_model_name: str,
    oc_config_path: Path = Path("/home/user/.openclaw/openclaw.json"),
) -> bool:
    """Return True if model already exists in openclaw.json.

    Checks openclaw.json (agents.defaults.models.<oc_model_name>).
    """

    oc_config_json_str = await read_file_as_text_async(oc_config_path)
    oc_config = json.loads(oc_config_json_str)

    agents = oc_config.get("agents")
    if not isinstance(agents, dict):
        return False

    defaults = agents.get("defaults")
    if not isinstance(defaults, dict):
        return False

    models = defaults.get("models")
    if not isinstance(models, dict):
        return False

    return oc_model_name in models


async def oc_add_model_via_cli(
    *,
    oc_model_name: str,
    runner: CommandRunner,
) -> CommandResult:
    """Add model into OpenClaw config via CLI.

    Uses: openclaw models set <model>
    """

    return await runner.exec_json(f"openclaw models set '{oc_model_name}'")


async def oc_restart_gateway(
    *,
    oc_session_key: str,
    oc_config_path: Path = Path("/home/user/.openclaw/openclaw.json"),
    chat_completions_url: str = "http://127.0.0.1:18789/v1/chat/completions",
) -> Any:
    """Restart gateway via /restart.

    Note: Restarting the gateway may terminate the HTTP request before a response
    is received. This function swallows such errors and returns None in that case.
    """

    oc_config_json_str = await read_file_as_text_async(oc_config_path)
    oc_config = json.loads(oc_config_json_str)
    token = oc_config.get("gateway", {}).get("auth", {}).get("token")

    headers = {
        "Authorization": f"Bearer {token}",
        "x-openclaw-session-key": oc_session_key,
    }
    payload = {
        "model": "openclaw",
        "messages": [{"role": "user", "content": "/restart"}],
        "stream": False,
    }

    try:
        return await fetch_json_with_retry(
            "POST",
            chat_completions_url,
            headers=headers,
            json=payload,
        )
    except Exception:
        return None


async def oc_set_session_model(
    *,
    oc_session_key: str,
    oc_model_name: str,
    oc_config_path: Path = Path("/home/user/.openclaw/openclaw.json"),
    chat_completions_url: str = "http://127.0.0.1:18789/v1/chat/completions",
) -> Any:
    """Switch session model via /model <name> and return raw JSON."""

    oc_config_json_str = await read_file_as_text_async(oc_config_path)
    oc_config = json.loads(oc_config_json_str)
    token = oc_config.get("gateway", {}).get("auth", {}).get("token")

    headers = {
        "Authorization": f"Bearer {token}",
        "x-openclaw-session-key": oc_session_key,
    }
    payload = {
        "model": "openclaw",
        "messages": [{"role": "user", "content": f"/model {oc_model_name}"}],
        "stream": False,
    }

    return await fetch_json_with_retry(
        "POST",
        chat_completions_url,
        headers=headers,
        json=payload,
        timeout=aiohttp.ClientTimeout(total=None, sock_read=120, connect=10)
    )


async def oc_update_session_model(
    *,
    oc_session_key: str,
    oc_model_name: str,
    oc_config_path: Path = Path("/home/user/.openclaw/openclaw.json"),
    chat_completions_url: str = "http://127.0.0.1:18789/v1/chat/completions",
    model_meta: dict | None = None,
) -> Any:
    """Update OpenClaw session model via /model <name>.

    Behavior:
    - Check whether model exists in openclaw.json.
    - If not, add it via `openclaw models set <model>`.
    - If added and oc_agent_id is provided, call /restart to reload gateway.
    - Then call /model <name> using x-openclaw-session-key.

    Returns the raw JSON response.
    """

    if model_meta is not None:
        # model_meta was previously used to directly patch openclaw.json.
        # This path is now intentionally CLI-driven.
        pass

    exists = await oc_has_model_in_openclaw_config(
        oc_model_name=oc_model_name,
        oc_config_path=oc_config_path,
    )
    added = False
    if not exists:
        runner = CommandRunner()
        await oc_add_model_via_cli(oc_model_name=oc_model_name, runner=runner)
        added = True

    # 模型通过 CLI 新增后，需要 /restart 才会让网关加载到新模型
    if added:
        await oc_restart_gateway(
            oc_session_key=oc_session_key,
            oc_config_path=oc_config_path,
            chat_completions_url=chat_completions_url,
        )

    # If the session already uses the same provider/model, skip calling /model.
    agent_name = _oc_extract_agent_name_from_session_key(oc_session_key)
    if agent_name:
        cur_provider, cur_model = await _oc_read_session_provider_model(
            oc_session_key=oc_session_key,
            oc_agent_name=agent_name,
        )
        cur_full = f"{cur_provider}/{cur_model}" if cur_provider and cur_model else ""
        if cur_full and cur_full == oc_model_name:
            log_info(f"{oc_model_name} model already set")
            return {"skipped": True, "reason": "model already set"}

    return await oc_set_session_model(
        oc_session_key=oc_session_key,
        oc_model_name=oc_model_name,
        oc_config_path=oc_config_path,
        chat_completions_url=chat_completions_url,
    )


async def oc_chat_completions_sse(
    *,
    oc_session_key: str,
    user_prompt: str,
    timeout: aiohttp.ClientTimeout | None = None,
    oc_config_path: Path = Path("/home/user/.openclaw/openclaw.json"),
    chat_completions_url: str = "http://127.0.0.1:18789/v1/chat/completions",
    model: str = "openclaw",
) -> Any:
    """Call OpenClaw /v1/chat/completions with stream=True and yield SSE events (bytes).

    Adds Authorization + x-openclaw-session-key headers.
    """
    oc_config_json_str = await read_file_as_text_async(oc_config_path)
    oc_config = json.loads(oc_config_json_str)
    token = oc_config.get("gateway", {}).get("auth", {}).get("token")

    headers = {"Authorization": f"Bearer {token}", "x-openclaw-session-key": oc_session_key}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": user_prompt}],
        "stream": True,
    }

    if timeout is None:
        timeout = aiohttp.ClientTimeout(total=None, sock_read=120, connect=10)

    async for event in fetch_sse_with_retry(
        "POST",
        chat_completions_url,
        headers=headers,
        json=payload,
        timeout=timeout,
    ):
        yield event