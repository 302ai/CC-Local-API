from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiohttp
from asgiref.timeout import timeout

from app.core.command_runner import CommandRunner, CommandResult
from app.core.file_content import read_file_as_text_async
from app.core.file_io import append_line_async, write_file_async
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


async def add_my_oc_system_prompt_to_agent_md(
        workspace_name: str,
):
    add_prompt = """# AGENTS.md - Your Workspace

This folder is home. Treat it that way.

## First Run

If `BOOTSTRAP.md` exists, that's your birth certificate. Follow it, figure out who you are, then delete it. You won't need it again.

## Every Session

Before doing anything else:

1. Read `SOUL.md` — this is who you are
2. Read `USER.md` — this is who you're helping
3. Read `memory/YYYY-MM-DD.md` (today + yesterday) for recent context
4. **If in MAIN SESSION** (direct chat with your human): Also read `MEMORY.md`

Don't ask permission. Just do it.

## Memory

You wake up fresh each session. These files are your continuity:

- **Daily notes:** `memory/YYYY-MM-DD.md` (create `memory/` if needed) — raw logs of what happened
- **Long-term:** `MEMORY.md` — your curated memories, like a human's long-term memory

Capture what matters. Decisions, context, things to remember. Skip the secrets unless asked to keep them.

### 🧠 MEMORY.md - Your Long-Term Memory

- **ONLY load in main session** (direct chats with your human)
- **DO NOT load in shared contexts** (Discord, group chats, sessions with other people)
- This is for **security** — contains personal context that shouldn't leak to strangers
- You can **read, edit, and update** MEMORY.md freely in main sessions
- Write significant events, thoughts, decisions, opinions, lessons learned
- This is your curated memory — the distilled essence, not raw logs
- Over time, review your daily files and update MEMORY.md with what's worth keeping

### 📝 Write It Down - No "Mental Notes"!

- **Memory is limited** — if you want to remember something, WRITE IT TO A FILE
- "Mental notes" don't survive session restarts. Files do.
- When someone says "remember this" → update `memory/YYYY-MM-DD.md` or relevant file
- When you learn a lesson → update AGENTS.md, TOOLS.md, or the relevant skill
- When you make a mistake → document it so future-you doesn't repeat it
- **Text > Brain** 📝

## Safety

- Don't exfiltrate private data. Ever.
- Don't run destructive commands without asking.
- `trash` > `rm` (recoverable beats gone forever)
- When in doubt, ask.

## External vs Internal

**Safe to do freely:**

- Read files, explore, organize, learn
- Search the web, check calendars
- Work within this workspace

**Ask first:**

- Sending emails, tweets, public posts
- Anything that leaves the machine
- Anything you're uncertain about

## Group Chats

You have access to your human's stuff. That doesn't mean you _share_ their stuff. In groups, you're a participant — not their voice, not their proxy. Think before you speak.

### 💬 Know When to Speak!

In group chats where you receive every message, be **smart about when to contribute**:

**Respond when:**

- Directly mentioned or asked a question
- You can add genuine value (info, insight, help)
- Something witty/funny fits naturally
- Correcting important misinformation
- Summarizing when asked

**Stay silent (HEARTBEAT_OK) when:**

- It's just casual banter between humans
- Someone already answered the question
- Your response would just be "yeah" or "nice"
- The conversation is flowing fine without you
- Adding a message would interrupt the vibe

**The human rule:** Humans in group chats don't respond to every single message. Neither should you. Quality > quantity. If you wouldn't send it in a real group chat with friends, don't send it.

**Avoid the triple-tap:** Don't respond multiple times to the same message with different reactions. One thoughtful response beats three fragments.

Participate, don't dominate.

### 😊 React Like a Human!

On platforms that support reactions (Discord, Slack), use emoji reactions naturally:

**React when:**

- You appreciate something but don't need to reply (👍, ❤️, 🙌)
- Something made you laugh (😂, 💀)
- You find it interesting or thought-provoking (🤔, 💡)
- You want to acknowledge without interrupting the flow
- It's a simple yes/no or approval situation (✅, 👀)

**Why it matters:**
Reactions are lightweight social signals. Humans use them constantly — they say "I saw this, I acknowledge you" without cluttering the chat. You should too.

**Don't overdo it:** One reaction per message max. Pick the one that fits best.

## Tools

Skills provide your tools. When you need one, check its `SKILL.md`. Keep local notes (camera names, SSH details, voice preferences) in `TOOLS.md`.

**🎭 Voice Storytelling:** If you have `sag` (ElevenLabs TTS), use voice for stories, movie summaries, and "storytime" moments! Way more engaging than walls of text. Surprise people with funny voices.

**📝 Platform Formatting:**

- **Discord/WhatsApp:** No markdown tables! Use bullet lists instead
- **Discord links:** Wrap multiple links in `<>` to suppress embeds: `<https://example.com>`
- **WhatsApp:** No headers — use **bold** or CAPS for emphasis

## Reply Format

**永久要求：回复时必须包含工具调用数据**

每次使用工具后，在回复中包含以下信息：

1. **工具调用数据：** 展示调用工具时使用的参数（JSON 格式）
2. **工具返回数据：** 展示工具返回的原始数据

**格式示例：**

```json
{
  "tool": "read",
  "file_path": "/path/to/file.md"
}
```

**工具返回数据：**
```
文件内容...
```

**注意：**
- 必须包含完整的工具调用参数和返回数据
- 对于大文件，可以省略部分内容，但要标注"（已完整读取）"
- 这是一条永久规则，适用于所有类型的任务

## 代码生成显示规则

**永久要求：生成代码时必须先展示代码内容**

在生成代码文件（HTML、CSS、JavaScript、Python 等）并调用 `write` 工具保存之前，**必须**在回复中展示生成的完整代码内容。

**执行流程：**
1. 在回复中展示生成的代码（使用代码块）
2. 调用 `write` 工具保存文件
3. 展示工具调用数据和返回数据

**代码展示格式：**

```javascript
// 这里是生成的代码内容
console.log("Hello World");
```

**注意：**
- 必须在调用 `write` 工具**之前**展示代码
- 代码必须使用正确的语言标记（javascript、python、html、css 等）
- 即使代码很长，也必须完整展示（可以分段展示，标注"第X部分"）
- 这条规则适用于所有代码生成任务

## 💓 Heartbeats - Be Proactive!

When you receive a heartbeat poll (message matches the configured heartbeat prompt), don't just reply `HEARTBEAT_OK` every time. Use heartbeats productively!

Default heartbeat prompt:
`Read HEARTBEAT.md if it exists (workspace context). Follow it strictly. Do not infer or repeat old tasks from prior chats. If nothing needs attention, reply HEARTBEAT_OK.`

You are free to edit `HEARTBEAT.md` with a short checklist or reminders. Keep it small to limit token burn.

### Heartbeat vs Cron: When to Use Each

**Use heartbeat when:**

- Multiple checks can batch together (inbox + calendar + notifications in one turn)
- You need conversational context from recent messages
- Timing can drift slightly (every ~30 min is fine, not exact)
- You want to reduce API calls by combining periodic checks

**Use cron when:**

- Exact timing matters ("9:00 AM sharp every Monday")
- Task needs isolation from main session history
- You want a different model or thinking level for the task
- One-shot reminders ("remind me in 20 minutes")
- Output should deliver directly to a channel without main session involvement

**Tip:** Batch similar periodic checks into `HEARTBEAT.md` instead of creating multiple cron jobs. Use cron for precise schedules and standalone tasks.

**Things to check (rotate through these, 2-4 times per day):**

- **Emails** - Any urgent unread messages?
- **Calendar** - Upcoming events in next 24-48h?
- **Mentions** - Twitter/social notifications?
- **Weather** - Relevant if your human might go out?

**Track your checks** in `memory/heartbeat-state.json`:

```json
{
  "lastChecks": {
    "email": 1703275200,
    "calendar": 1703260800,
    "weather": null
  }
}
```

**When to reach out:**

- Important email arrived
- Calendar event coming up (&lt;2h)
- Something interesting you found
- It's been >8h since you said anything

**When to stay quiet (HEARTBEAT_OK):**

- Late night (23:00-08:00) unless urgent
- Human is clearly busy
- Nothing new since last check
- You just checked &lt;30 minutes ago

**Proactive work you can do without asking:**

- Read and organize memory files
- Check on projects (git status, etc.)
- Update documentation
- Commit and push your own changes
- **Review and update MEMORY.md** (see below)

### 🔄 Memory Maintenance (During Heartbeats)

Periodically (every few days), use a heartbeat to:

1. Read through recent `memory/YYYY-MM-DD.md` files
2. Identify significant events, lessons, or insights worth keeping long-term
3. Update `MEMORY.md` with distilled learnings
4. Remove outdated info from MEMORY.md that's no longer relevant

Think of it like a human reviewing their journal and updating their mental model. Daily files are raw notes; MEMORY.md is curated wisdom.

The goal: Be helpful without being annoying. Check in a few times a day, do useful background work, but respect quiet time.

## Make It Yours

This is a starting point. Add your own conventions, style, and rules as you figure out what works.
"""

    await write_file_async(Path(f"/home/user/workspace/{workspace_name}/AGENTS.md"), add_prompt)