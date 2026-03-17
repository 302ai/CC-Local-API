from __future__ import annotations

import asyncio
import base64
import binascii
from datetime import datetime, timezone
import json
import mimetypes
import os
import re
import secrets
import shlex
import string
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, Optional, List, Literal, Union, Tuple
from urllib.parse import quote, urlparse

import aiohttp
from fastapi import APIRouter, Depends, Request, Query
from starlette.responses import StreamingResponse

from app.api.response import fail, ok, oc_fail_stream, gpt_stream_chunk
from app.api.routes_command import sse_message
from app.api.routes_session import claw_lock
from app.core.ai302.deploy_ops import create_302ai_deploy_task, get_302ai_deploy_task_info
from app.core.command_parser import parse_command_from_message, CommandType
from app.core.command_runner import CommandRunner
from app.core.config import ROOT_SAVE_PATH, settings
from app.core.file_content import create_zip_from_directory, read_file_as_text_async
from app.core.file_io import download_file_from_url, write_file_async
from app.core.log import log_error, log_info, log_warning
from app.core.oc_ops import oc_new_session_and_list_active, oc_update_session_model, oc_chat_completions_sse, \
    add_my_oc_system_prompt_to_agent_md
from app.db.session import get_db, run_in_threadpool
from app.repositories.session_repo import SessionRepository


from pydantic import BaseModel, Field

from app.utils.utils import get_uuid
from claude_md import claude_md_str

router = APIRouter()

_MIME_TO_EXT = {
    # ---------- images ----------
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/pjpeg": ".jpg",
    "image/png": ".png",
    "image/apng": ".apng",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/x-ms-bmp": ".bmp",
    "image/tiff": ".tif",
    "image/x-icon": ".ico",
    "image/vnd.microsoft.icon": ".ico",
    "image/heic": ".heic",
    "image/heif": ".heif",
    "image/avif": ".avif",
    "image/svg+xml": ".svg",

    # ---------- documents / text ----------
    "application/pdf": ".pdf",
    "text/plain": ".txt",
    "text/markdown": ".md",
    "text/html": ".html",
    "text/css": ".css",
    "text/csv": ".csv",
    "text/tab-separated-values": ".tsv",
    "application/json": ".json",
    "application/ld+json": ".jsonld",
    "application/xml": ".xml",
    "text/xml": ".xml",
    "application/yaml": ".yaml",
    "text/yaml": ".yaml",
    "application/x-yaml": ".yaml",
    "application/rtf": ".rtf",

    # ---------- office ----------
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-powerpoint": ".ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.ms-outlook": ".msg",

    # ---------- archives ----------
    "application/zip": ".zip",
    "application/x-zip-compressed": ".zip",
    "application/x-7z-compressed": ".7z",
    "application/x-rar-compressed": ".rar",
    "application/x-tar": ".tar",
    "application/gzip": ".gz",
    "application/x-gzip": ".gz",
    "application/x-bzip2": ".bz2",
    "application/x-xz": ".xz",

    # ---------- audio ----------
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/flac": ".flac",
    "audio/aac": ".aac",
    "audio/ogg": ".ogg",
    "audio/opus": ".opus",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/webm": ".weba",
    "audio/midi": ".mid",
    "audio/x-midi": ".mid",

    # ---------- video ----------
    "video/mp4": ".mp4",
    "video/mpeg": ".mpeg",
    "video/quicktime": ".mov",
    "video/x-msvideo": ".avi",
    "video/x-ms-wmv": ".wmv",
    "video/webm": ".webm",
    "video/ogg": ".ogv",
    "video/x-matroska": ".mkv",
    "video/3gpp": ".3gp",
    "video/3gpp2": ".3g2",

    # ---------- fonts ----------
    "font/ttf": ".ttf",
    "font/otf": ".otf",
    "font/woff": ".woff",
    "font/woff2": ".woff2",
    "application/font-woff": ".woff",
    "application/font-woff2": ".woff2",

    # ---------- binaries / misc ----------
    "application/octet-stream": "",  # 不确定就留空，交给内容识别/文件名
    "application/x-msdownload": ".exe",

    # ---------- common code/config ----------
    "application/javascript": ".js",
    "text/javascript": ".js",
    "application/x-python-code": ".py",
}

# 需要排除的目录和文件模式
EXCLUDE_PATTERNS = {
    "node_modules",
    ".git",
    ".svn",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    ".idea",
    ".vscode",
    ".DS_Store",
    ".cache",
    "coverage",
    ".pytest_cache",
    ".egg-info",
    ".tox",
    "target",
    "vendor",
    "bin",
    "obj",
    ".next",
    ".nuxt",
    "bower_components",
}

class TextContent(BaseModel):
    type: Literal["text"] = Field(default="text", description="内容类型")
    text: str = Field(..., description="文本内容")

class ImageContent(BaseModel):
    type: Literal["image_url"] = Field(default="image_url", description="内容类型")
    image_url: dict = Field(..., description="图片URL信息")


class Message(BaseModel):
    role: Literal["user", "assistant", "system", "tool"] = Field(..., description="消息角色")
    content: Union[str, List[Union[TextContent, ImageContent]]] = Field(..., description="消息内容")

    class Config:
        extra = "allow"


class ClaudeChatCompletionRequest(BaseModel):
    model: str = Field(..., description="模型名称")
    # max_tokens: int = Field(1024, description="最大生成token数", gt=0)
    messages: List[Message] = Field(..., description="对话消息列表")
    stream: bool = Field(True, description="是否流式输出")
    structured_output: bool = Field(False, description="是否以CC原始结构输出")
    enable_pre_deploy_check: bool = Field(False, description="是否开启部署前检测 需要开启structured_output使用")
    available_skills: List[str] = Field([], description="对话选择开启的skills")
    action: str = Field("", description="特殊操作指令")
    agent_type: int = Field(0, description="智能体类型， 0=claude code；1=openclaw")

    class Config:
        extra = "allow"


def get_session_repo(db=Depends(get_db)) -> SessionRepository:
    return SessionRepository(db)



@router.post("/chat/completions")
async def stream_chat(request: Request, payload: ClaudeChatCompletionRequest, repo: SessionRepository = Depends(get_session_repo)):

    if not payload.messages or len(payload.messages) == 0:
        return fail("messages is empty")

    runner = CommandRunner()

    async def gen():

        async def _run_claude_code_cmd():
            # 判断用户是否有传入session
            session_id = await run_in_threadpool(
                lambda: _get_field_value(payload, request, "session_id")
            )
            # 没传入 生成默认的session_id
            if not session_id:
                session_id = str(uuid.uuid4())
            # 数据库不存在视为全新的对话， 并创建工作目录
            with repo.atomic():
                session = repo.get_session_by_alias(session_id)
                if session is None:
                    workspace_path = f"{ROOT_SAVE_PATH}/workspace/{_secure_rand_str()}"
                    os.makedirs(workspace_path, exist_ok=True)
                    session = repo.create_session(
                        session_alias=session_id,
                        workspace_path=workspace_path,
                    )
                    cc_session_id = ""

                else:
                    workspace_path = session.workspace_path
                    cc_session_id = session.session_id
            await write_file_async(Path(f"{workspace_path}/CLAUDE.md"), claude_md_str)
            yield sse_message("session_id", {"session_id": session_id, "workspace_path": workspace_path})

            # 处理模型信息
            # fix 旧逻辑model传在线沙盒id，如果model以302-sandbox-开头，直接先使用环境默认变量里的模型
            # 现在线上版本的逻辑是四个模型参数全用同一个模型  这里也保持一致
            haiku_model = settings.ANTHROPIC_DEFAULT_HAIKU_MODEL if payload.model.startswith(
                "302-sandbox-") else payload.model

            opus_model = settings.ANTHROPIC_DEFAULT_OPUS_MODEL if payload.model.startswith(
                "302-sandbox-") else payload.model

            sonnet_model = settings.ANTHROPIC_DEFAULT_SONNET_MODEL if payload.model.startswith(
                "302-sandbox-") else payload.model

            subagent_model = settings.CLAUDE_CODE_SUBAGENT_MODEL if payload.model.startswith(
                "302-sandbox-") else payload.model

            envs = {
                "BASH_DEFAULT_TIMEOUT_MS": "600000",
                "BASH_MAX_TIMEOUT_MS": "1200000",
                "ANTHROPIC_DEFAULT_OPUS_MODEL": opus_model,
                "ANTHROPIC_DEFAULT_SONNET_MODEL": sonnet_model,
                "ANTHROPIC_DEFAULT_HAIKU_MODEL": haiku_model,
                "CLAUDE_CODE_SUBAGENT_MODEL": subagent_model
            }

            # 保存附件文件
            file_paths = await _save_attachments(files, workspace_path)

            # 判断是否强制把skill.md塞入上下文 前端将skill md作为tool类型messag发送 tool_call_id以forced-skill开头
            forced_skill_tool = [x for x in payload.messages if x.role == "tool" and hasattr(x, "tool_call_id") and x.tool_call_id.startswith("forced-skill")]
            if forced_skill_tool:
                cc_history_project_path = f"/home/user/.claude/projects/{workspace_path.replace('/', '-')}"
                # 首次对话缺少上下文历史jsonl文件 CC的CLI不支持/init 手动伪造JSONL会导致CC会报错 直接先进行一次简单的对话作为项目的初始化
                if not cc_session_id:
                    actively_set_session_id = get_uuid()
                    init_input = "初始化项目，请直接回答你好并就结束任务（本次对话不使用任何MCP和skill和tool，但这个要求不要带到接下来的其他对话上）"
                    init_session_resp = await runner.exec_json(f"echo '{init_input}' | claude -p --dangerously-skip-permissions true --session-id {actively_set_session_id} ",
                                                               cwd=workspace_path,
                                                               timeout=300,
                                                               env=envs)
                    if init_session_resp.exit_code != 0:
                        yield  f"data: Init Failed: {init_session_resp.stderr}\n\n"
                        return
                    cc_session_id = actively_set_session_id
                cc_history_project_jsonl = f'{cc_history_project_path}/{cc_session_id}.jsonl'

                qa_list = []
                for message in forced_skill_tool:
                    qa_list.append((f"{MANUAL_INSERT_PREFIX} ", message.content))
                if qa_list:
                    cc_history_project_jsonl_content = await read_file_as_text_async(Path(cc_history_project_jsonl))
                    result = await run_in_threadpool(
                        lambda: _generate_qa_batch_content(cc_history_project_jsonl_content, qa_list)
                    )
                    if result:
                        await write_file_async(Path(cc_history_project_jsonl), result["full_content"])
                        log_info(f"成功生成 {result['count']} 组问答，移除了 {result['removed_count']} 条旧记录")
                    else:
                        log_warning("追加失败")
            # 判断是否是plan模式
            is_plan = True if payload.action == "plan" else False
            final_user_prompt = user_prompt + " " + ",".join(file_paths) + " ,当前的工作目录是：" + workspace_path + f" ,附件目录是： {workspace_path}/.302ai/attachments"
            if payload.available_skills:
                skill_prompt_prefix = "**Note**:  忽略之前提及的skills存储位置， 你使用的skills以接下来我告诉你的路径为准"
                for skill in payload.available_skills:
                    find_skill_path = await run_in_threadpool(
                        lambda: _find_folder_upto_depth2("/home/user/.claude/skills", skill)
                    )
                    if find_skill_path:
                        final_user_prompt += f"\n {skill_prompt_prefix}{skill} skill数据存放在： {','.join(find_skill_path)}"
                        skill_prompt_prefix = ""
            log_info(final_user_prompt)
            claude_code_cmd = await run_in_threadpool(
                lambda: _build_claude_command(
                    final_user_prompt,
                    cc_session_id,
                    system_prompt, is_plan_mode=is_plan)
            )

            log_info(claude_code_cmd)
            # 判断是否传max_thinking_token
            max_thinking_token = 0
            if hasattr(payload, "max_thinking_token") and isinstance(payload.max_thinking_token, int):
                max_thinking_token = payload.max_thinking_token
            envs["MAX_THINKING_TOKENS"] = str(max_thinking_token)

            is_save_session = False
            run_id: Optional[str] = None
            try:
                async for ev in runner.stream(
                        claude_code_cmd,
                        cwd=workspace_path,
                        env=envs,
                        timeout=1800,
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
                    elif event == "heartbeat":
                        if payload.structured_output:
                            heartbeat = json.dumps({
                                "type": "heartbeat",
                                "timestamp": time.time()
                            })
                            yield f"data: {heartbeat}\n\n"
                    elif event == "warning":
                        log_warning(ev["text"])
                    elif event == "output":

                        def bind_op(sid, true_sid):
                            def op():
                                with repo.atomic():
                                    return repo.bind_session_id(sid, true_sid)

                            return op

                        try:
                            output_stream_json = json.loads(ev["text"])
                            true_session_id = output_stream_json.get("session_id", "")
                            if not is_save_session and true_session_id:
                                # 第一次获取到CC真正的session_id,存一次
                                session = await run_in_threadpool(bind_op(session.id, true_session_id))
                                is_save_session = True
                                log_info(f"Updated session_id: {true_session_id}")
                                log_info(
                                    f"session id: {session.id}, workspace_path: {session.workspace_path}, note: {session.note}, alias: {session.session_alias}")
                            # 最后result流再存一次
                            if output_stream_json.get("type", "") == "result":
                                session = await run_in_threadpool(bind_op(session.id, true_session_id))
                        except Exception as e:
                            log_error(f"The operation stream-json stream failed： {e}")

                        yield f"data: {ev['text']}\n\n"
                        # yield sse_message("output", {"run_id": ev["run_id"], "text": ev["text"]})
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

            check_cmd = """find . -maxdepth 4 \( -path "./claude" -o -path "./claude/*" -o -path "./node_modules" -o -path "./node_modules/*" -o -path "./.git" -o -path "./.git/*" -o -path "./venv" -o -path "./venv/*" -o -path "./.venv" -o -path "./.venv/*" -o -path "./env" -o -path "./env/*" -o -path "./__pycache__" -o -path "./__pycache__/*" \) -prune -o -type f \( -name "package.json" -o -name "pnpm-lock.yaml" -o -name "yarn.lock" -o -name "package-lock.json" -o -name "next.config.*" -o -name "vite.config.*" -o -name "vue.config.*" -o -name "nuxt.config.*" -o -name "svelte.config.*" -o -name "astro.config.*" -o -name "remix.config.*" -o -name "angular.json" -o -name "gatsby-config.*" -o -path "./index.html" -o -path "*/public/index.html" -o -path "./server.js" -o -path "./app.js" -o -path "./index.js" -o -path "./main.js" -o -path "./server.ts" -o -path "./app.ts" -o -path "./index.ts" -o -path "./main.ts" -o -path "./src/index.js" -o -path "./src/index.ts" -o -path "./src/index.jsx" -o -path "./src/index.tsx" -o -path "./src/main.js" -o -path "./src/main.ts" -o -path "./src/main.jsx" -o -path "./src/main.tsx" -o -path "./src/App.vue" -o -path "./src/app.js" -o -path "./src/app.ts" -o -path "./src/app.jsx" -o -path "./src/app.tsx" -o -path "./src/server.js" -o -path "./src/server.ts" -o \( -path "./src/*" -a \( -name "*.js" -o -name "*.ts" -o -name "*.jsx" -o -name "*.tsx" -o -name "*.vue" \) \) \)"""

            if payload.enable_pre_deploy_check:

                pre_deploy_check_result = await runner.exec_json(command=check_cmd, cwd=workspace_path)
                if pre_deploy_check_result.exit_code == 0:
                    if pre_deploy_check_result.stdout:
                        deploy_check_info = json.dumps({
                            "type": "pre_deploy_check",
                            "success": True,
                            "find_file": pre_deploy_check_result.stdout,
                        })
                    else:
                        deploy_check_info = json.dumps({
                            "type": "pre_deploy_check",
                            "success": False,
                            "find_file": pre_deploy_check_result.stdout,
                        })
                    yield f"data: {deploy_check_info}\n\n"

        async def _run_custom_cmd():
            cmd_data = parse_command_result.data
            command = cmd_data.command
            work_path = cmd_data.cwd
            envs = cmd_data.envs or {}

            run_id: Optional[str] = None
            try:
                async for ev in runner.stream(
                        command,
                        cwd=work_path,
                        env=envs,
                        timeout=600,
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
                        yield f"data: {ev['text']}\n\n"
                        # yield sse_message("output", {"run_id": ev["run_id"], "text": ev["text"]})
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

        async def _run_deploy_cmd():
            # 判断用户是否有传入session
            session_id = await run_in_threadpool(
                lambda: _get_field_value(payload, request, "session_id")
            )
            # 没传入 生成默认的session_id
            if not session_id:
                yield f"event: error\ndata: Missing session_id\n\n"
                return
            session = repo.get_session_by_alias(session_id)
            if session is None:
                yield f"event: error\ndata: Not found session_id: {session_id}\n\n"
                return
            workspace_path = session.workspace_path

            if parse_command_result.data.envs:
                env_content = "\n".join(
                    f"{key}={value}"
                    for key, value in parse_command_result.data.envs.items()
                )
                await write_file_async(Path(f"{workspace_path}/.env"), env_content)

            # 用户使用自己的vercel key
            if parse_command_result.data.vercel_key:
                project_name = parse_command_result.data.project_name or _secure_rand_str()

                vercel_line_result = await runner.exec_json(
                    command=f"vercel link --project {project_name} --token={parse_command_result.data.vercel_key} --yes",
                    cwd=workspace_path
                )
                if vercel_line_result.exit_code != 0:
                    yield f"event: error\ndata: Failed to deploy: {vercel_line_result.stderr}\n\n"
                    return

                deploy_result = await runner.exec_json(
                    command=f"vercel --prod --token={parse_command_result.data.vercel_key} --yes",
                    cwd=workspace_path
                )
                if deploy_result.exit_code != 0:
                    yield f"event: error\ndata: Failed to deploy: {deploy_result.stderr}\n\n"
                    return

                resp = json.dumps({
                    "type": "deploy_success",
                    "success": True,
                    "status": "success",
                    "id": "",
                    "url": deploy_result.stdout,
                    "cover": ""
                })
                yield f"data: {resp}\n\n"

            else:
                AI302_API_KEY = os.environ.get("AI302_API_KEY", "")
                if not AI302_API_KEY:
                    yield f"event: error\ndata: Missing AI302_API_KEY\n\n"
                    return

                zip_path = await run_in_threadpool(
                    lambda: create_zip_from_directory(workspace_path, exclude_patterns=EXCLUDE_PATTERNS)
                )

                if zip_path.stat().st_size > 20 * 1024 * 1024:
                    yield f"event: error\ndata: The file data is too large and exceeds the size limit of the 302.ai deployment interface\n\n"
                    return

                try:
                    headers = {'Authorization': f"Bearer {AI302_API_KEY}"}
                    create_deploy_task_resp = await create_302ai_deploy_task(zip_path, headers=headers, update_subdomain=session.deploy_id)
                    deploy_project_id = create_deploy_task_resp["id"]
                    session = await run_in_threadpool(
                        lambda: repo.update_session(session.id, deploy_id=deploy_project_id)
                    )
                    # 发送部署任务创建成功的消息
                    task_created = json.dumps({
                        "type": "deploy_task_created",
                        "id": deploy_project_id,
                        "message": "Deploy task created, waiting for completion..."
                    })
                    yield f"data: {task_created}\n\n"

                    for i in range(30):
                        await asyncio.sleep(10)

                        # 发送轮询进度心跳
                        progress = json.dumps({
                            "type": "deploy_progress",
                            "attempt": i + 1,
                            "max_attempts": 30,
                            "timestamp": time.time()
                        })
                        yield f"data: {progress}\n\n"

                        deploy_result = await get_302ai_deploy_task_info(deploy_project_id, headers=headers)
                        if deploy_result["success"]:
                            if deploy_result["status"] == "success":
                                resp = json.dumps({
                                    "type": "deploy_success",
                                    "success": True,
                                    "status": "success",
                                    "id": deploy_project_id,
                                    "url": deploy_result["url"],
                                    "cover": ""
                                })
                                yield f"data: {resp}\n\n"
                                return
                        else:
                            yield f"event: error\ndata: Deploy sandbox failed: {deploy_result['error']}\n\n"
                            return

                    yield f"event: error\ndata: Deploy sandbox failed: Wait for a timeout\n\n"
                    return
                except Exception as e:
                    yield f"event: error\ndata: Deploy sandbox failed: {e}\n\n"
                    return

        async def _run_plugin_cmd():
            plugin_agent = "openclaw" if payload.agent_type == 1 else "claude"
            plugin_cmd = f"{plugin_agent} plugin {parse_command_result.data.plugin_args}"
            log_info(f"plugin_cmd: {plugin_cmd}")
            plugin_cmd_resp = await runner.exec_json(plugin_cmd)
            if plugin_cmd_resp.exit_code == 0:
                log_info(plugin_cmd_resp.stdout)
                yield "data: **Plugin successfully**\n\n"
                yield f"data: {plugin_cmd_resp.stdout}\n\n"
            else:
                log_error(plugin_cmd_resp.stderr)
                yield "data: **Plugin failed**\n\n"
                yield f"data: {plugin_cmd_resp.stderr}\n\n"

        async def _run_openclaw_cmd():
            # 判断用户是否有传入session
            session_id = await run_in_threadpool(
                lambda: _get_field_value(payload, request, "session_id")
            )
            # 没传入 生成默认的session_id
            if not session_id:
                session_id = str(uuid.uuid4())

            session = repo.get_session_by_alias(session_id)

            if session is None:
                async with claw_lock:
                    workspace_path = f"{ROOT_SAVE_PATH}/workspace/{_secure_rand_str()}"
                    workspace_name = Path(workspace_path).name
                    create_agent_cmd = f"openclaw agents add --workspace '{workspace_path}' '{workspace_name}' --json"
                    create_agent_result = await runner.exec_json(create_agent_cmd)
                    if create_agent_result.exit_code != 0:
                        raise Exception(create_agent_result.stderr)
                    log_info(f"create agent {workspace_path} success\n{create_agent_result.stdout}")
                    await add_my_oc_system_prompt_to_agent_md(workspace_name)
                    oc_agent_id = workspace_name
                    new_resp, list_sessions_result = await oc_new_session_and_list_active(
                        oc_agent_id=oc_agent_id,
                        runner=runner,
                        active=3,
                    )
                    log_info(f"{new_resp}")

                    if list_sessions_result.exit_code != 0:
                        raise Exception(list_sessions_result.stderr)
                    log_info(list_sessions_result.stdout)
                    data = json.loads(list_sessions_result.stdout)
                    sessions = data.get("sessions", [])

                    if not sessions:
                        raise Exception("No active sessions found")

                    # 按 updatedAt 降序排序，取最新的一个
                    latest_session = max(sessions, key=lambda s: s.get("updatedAt", 0))
                    log_info(f"{latest_session}")

                session = await run_in_threadpool(lambda: repo.create_session(
                    session_alias=payload.session_id,
                    workspace_path=workspace_path,
                    oc_agent_id=oc_agent_id,
                    oc_session_id=latest_session.get("sessionId"),
                    oc_session_key=latest_session.get("key"),
                ))
                oc_session_key = latest_session.get("key")
            else:
                if not session.oc_session_key:
                    workspace_path = session.workspace_path
                    oc_agent_id = repo.get_oc_agent_id_by_workspace_path(workspace_path)
                    if not oc_agent_id:
                        workspace_name = Path(workspace_path).name  # 直接将工作区的名字作为OC的agent名
                        create_agent_cmd = f"openclaw agents add --workspace '{workspace_path}' '{workspace_name}' --json"
                        create_agent_result = await runner.exec_json(create_agent_cmd)
                        if create_agent_result.exit_code != 0:
                            raise Exception(create_agent_result.stderr)
                        log_info(f"create agent {workspace_path} success\n{create_agent_result.stdout}")
                        await add_my_oc_system_prompt_to_agent_md(workspace_name)
                        oc_agent_id = workspace_name
                        # 先保存一次OC agent信息
                        session = await run_in_threadpool(lambda: repo.update_session(
                            id=session.id,
                            oc_agent_id=oc_agent_id,
                        ))
                    new_resp, list_sessions_result = await oc_new_session_and_list_active(
                        oc_agent_id=oc_agent_id,
                        runner=runner,
                        active=3,
                    )
                    log_info(f"{new_resp}")

                    if list_sessions_result.exit_code != 0:
                        raise Exception(list_sessions_result.stderr)

                    data = json.loads(list_sessions_result.stdout)
                    sessions = data.get("sessions", [])

                    if not sessions:
                        raise Exception("No active sessions found")

                    # 按 updatedAt 降序排序，取最新的一个
                    latest_session = max(sessions, key=lambda s: s.get("updatedAt", 0))
                    log_info(f"{latest_session}")
                    session = await run_in_threadpool(lambda: repo.update_session(
                        id=session.id,
                        oc_agent_id=oc_agent_id,
                        oc_session_id=latest_session.get("sessionId"),
                        oc_session_key=latest_session.get("key"),
                    ))
                    oc_session_key = latest_session.get("key")
                else:
                    oc_session_key = session.oc_session_key
                    oc_agent_id = session.oc_agent_id
                    workspace_path = session.workspace_path

            # 通过oc的/chat/completions接口的/model命令重新设置模型
            if payload.model.startswith("cc-") or payload.model.endswith("-for-coding"):
                await oc_update_session_model(oc_session_key=oc_session_key, oc_model_name=f"ai302-coding/{payload.model}")
            else:
                await oc_update_session_model(oc_session_key=oc_session_key, oc_model_name=f"ai302/{payload.model}")

            # 保存附件文件
            file_paths = await _save_attachments(files, workspace_path)

            # 拷贝claude.md
            await write_file_async(Path(f"{workspace_path}/CLAUDE.md"), claude_md_str)
            if user_prompt.lstrip().startswith("/"):
                final_user_prompt = user_prompt
            else:
                final_user_prompt = user_prompt  + " " + ",".join(
                    file_paths) + " ,当前的工作目录是：" + workspace_path + f" ,附件目录是： {workspace_path}/.302ai/attachments" + f" ,如果是编程相关任务，请先阅读{workspace_path}/CLAUDE.md，里面有我的开发习惯"
            async for event in oc_chat_completions_sse(
                    oc_session_key=oc_session_key,
                    user_prompt=final_user_prompt,
                    timeout=aiohttp.ClientTimeout(total=None, sock_read=None, connect=30),
            ):
                # event 是 bytes，需要对应处理
                if event.strip() == b"data: [DONE]":

                    check_cmd = """find . -maxdepth 4 \( -path "./claude" -o -path "./claude/*" -o -path "./node_modules" -o -path "./node_modules/*" -o -path "./.git" -o -path "./.git/*" -o -path "./venv" -o -path "./venv/*" -o -path "./.venv" -o -path "./.venv/*" -o -path "./env" -o -path "./env/*" -o -path "./__pycache__" -o -path "./__pycache__/*" \) -prune -o -type f \( -name "package.json" -o -name "pnpm-lock.yaml" -o -name "yarn.lock" -o -name "package-lock.json" -o -name "next.config.*" -o -name "vite.config.*" -o -name "vue.config.*" -o -name "nuxt.config.*" -o -name "svelte.config.*" -o -name "astro.config.*" -o -name "remix.config.*" -o -name "angular.json" -o -name "gatsby-config.*" -o -path "./index.html" -o -path "*/public/index.html" -o -path "./server.js" -o -path "./app.js" -o -path "./index.js" -o -path "./main.js" -o -path "./server.ts" -o -path "./app.ts" -o -path "./index.ts" -o -path "./main.ts" -o -path "./src/index.js" -o -path "./src/index.ts" -o -path "./src/index.jsx" -o -path "./src/index.tsx" -o -path "./src/main.js" -o -path "./src/main.ts" -o -path "./src/main.jsx" -o -path "./src/main.tsx" -o -path "./src/App.vue" -o -path "./src/app.js" -o -path "./src/app.ts" -o -path "./src/app.jsx" -o -path "./src/app.tsx" -o -path "./src/server.js" -o -path "./src/server.ts" -o \( -path "./src/*" -a \( -name "*.js" -o -name "*.ts" -o -name "*.jsx" -o -name "*.tsx" -o -name "*.vue" \) \) \)"""

                    if payload.enable_pre_deploy_check:

                        pre_deploy_check_result = await runner.exec_json(command=check_cmd, cwd=workspace_path)
                        if pre_deploy_check_result.exit_code == 0:
                            if pre_deploy_check_result.stdout:
                                deploy_check_info = json.dumps({
                                    "type": "pre_deploy_check",
                                    "success": True,
                                    "find_file": pre_deploy_check_result.stdout,
                                })
                            else:
                                deploy_check_info = json.dumps({
                                    "type": "pre_deploy_check",
                                    "success": False,
                                    "find_file": pre_deploy_check_result.stdout,
                                })

                            # 插入自定义文本 chunk
                            chunk = gpt_stream_chunk(f"{json.dumps(deploy_check_info, ensure_ascii=False)}")
                            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode("utf-8")
                    # 放行 [DONE]
                    yield event
                else:
                    yield event

        # 处理messages
        system_prompt, user_prompt, last_user_prompt, files = await run_in_threadpool(
            lambda: _extract_prompts(payload.messages)
        )

        request_headers = dict(request.headers)
        if hasattr(payload, "session_id") and payload.session_id:
            request_headers["session_id"] = payload.session_id
        parse_command_result = await parse_command_from_message(user_prompt, request_headers)
        log_info(f"parse_command_result: {parse_command_result}")
        # 用户输入了预设的斜杠命令
        if parse_command_result:
            command_handlers = {
                CommandType.COMMAND: _run_custom_cmd,
                CommandType.DEPLOY: _run_deploy_cmd,
                CommandType.PLUGIN: _run_plugin_cmd,
            }

            handler = command_handlers.get(parse_command_result.command_type)
            if handler:
                async for chunk in handler():
                    await asyncio.sleep(0)
                    yield chunk
        else:
            if payload.agent_type == 0:
                async for chunk in _run_claude_code_cmd():
                    await asyncio.sleep(0)
                    yield chunk
            else:
                try:
                    async for chunk in _run_openclaw_cmd():
                        await asyncio.sleep(0)
                        yield chunk
                except Exception as e:
                    traceback.print_exc()
                    async for chunk in oc_fail_stream(str(e)):
                        await asyncio.sleep(0)
                        yield chunk

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _secure_rand_str(n=10):
    alphabet = string.ascii_lowercase + string.digits  # a-z + 0-9
    return ''.join(secrets.choice(alphabet) for _ in range(n))


def _get_field_value(payload: BaseModel, request: Request, field_name: str, default: str = "") -> str:
        """
        优先从 payload 获取字段值，其次从 headers 获取，都不存在返回默认值

        Args:
            payload: Pydantic 模型实例
            request: FastAPI Request 对象
            field_name: 字段名称
            default: 默认值，默认为空字符串

        Returns:
            字段值或默认值
        """
        # 1. 优先从 payload 获取
        value = getattr(payload, field_name, None)
        if value is not None and value != "":
            return str(value) if not isinstance(value, str) else value

        # 2. 从 headers 获取（headers 通常用 X- 前缀或 - 连接）
        # 尝试多种 header 命名格式
        header_variants = [
            field_name,  # 原始名称: user_id
            field_name.replace("_", "-"),  # 下划线转横线: user-id
            f"X-{field_name}",  # 加 X- 前缀: X-user_id
            f"X-{field_name.replace('_', '-')}",  # X- 前缀 + 横线: X-user-id
        ]

        for header_name in header_variants:
            header_value = request.headers.get(header_name)
            if header_value is not None and header_value != "":
                return header_value

        # 3. 都不存在返回默认值
        return default


def _extract_prompts(messages: List[Message]) -> Tuple[Optional[str], str, str, List[dict]]:
    """
    从消息列表中提取系统提示词、用户提示词、上次用户提示词和图片URL列表
    用户提示词必定存在，没有user角色时取最后一条
    如果previous_user_prompt是命令（/deploy /model /command开头），则继续向上查找

    Returns:
        Tuple[Optional[str], str, str, List[dict]]: (系统提示词, 用户提示词, 上次用户提示词, 图片列表)
    """
    if not messages:
        raise ValueError("消息列表不能为空")

    def extract_content(content: Union[str, List]) -> Tuple[str, List[str]]:
        """提取文本和图片URL"""
        if isinstance(content, str):
            return content, []

        texts = []
        images = []

        for item in content:
            # 兼容dict和Pydantic模型
            if hasattr(item, 'model_dump'):
                item = item.model_dump()

            if isinstance(item, dict):
                if item.get("type") == "text":
                    texts.append(item.get("text", ""))
                elif item.get("type") == "image_url":
                    url = item.get("image_url", {}).get("url", "")
                    if url:
                        images.append(item)

        return " ".join(texts) if texts else "", images

    def is_command(text: str) -> bool:
        """检查文本是否是命令"""
        commands = ['/deploy', '/model', '/command', '/max_thinking_token']
        return any(text.strip().startswith(cmd) for cmd in commands)

    def find_previous_non_command_prompt(user_messages: List[Message], start_index: int) -> str:
        """从指定索引开始向前查找非命令的用户提示词"""
        for i in range(start_index, -1, -1):
            text, _ = extract_content(user_messages[i].content)
            if not is_command(text):
                return text
        return ""

    # 只有一条消息时
    if len(messages) == 1:
        text, images = extract_content(messages[0].content)
        return None, text, "", images  # 上次用户提示词为空

    # 提取系统提示词（只取文本部分）
    system_prompt = None
    for msg in messages:
        if msg.role == "system":
            system_prompt, _ = extract_content(msg.content)
            break

    # 提取用户提示词和图片
    user_messages = [msg for msg in messages if msg.role == "user"]

    # 初始化返回值
    user_prompt = ""
    previous_user_prompt = ""
    images = []

    if user_messages:
        # 获取最后一条用户消息
        user_prompt, images = extract_content(user_messages[-1].content)

        # 如果有多条用户消息，查找上一条非命令的用户提示词
        if len(user_messages) >= 2:
            # 从倒数第二条开始向前查找
            previous_user_prompt = find_previous_non_command_prompt(user_messages, len(user_messages) - 2)
    else:
        # 没有user角色时取最后一条
        user_prompt, images = extract_content(messages[-1].content)

    return system_prompt, user_prompt, previous_user_prompt, images


def _safe_filename(name: str) -> str:
    name = (name or "").strip().replace("\\", "_").replace("/", "_")
    name = re.sub(r"[^0-9A-Za-z._-]+", "_", name)
    name = name.strip("._")
    return name or f"file_{uuid.uuid4().hex}"

def _guess_ext(content: bytes, mime: str | None = None) -> str:
    if mime:
        ext = _MIME_TO_EXT.get(mime.lower())
        if ext:
            return ext
        ext = mimetypes.guess_extension(mime.lower())
        if ext:
            return ext

    return ""  # 实在识别不了就不加后缀

def _parse_file_item(file: dict) -> tuple[bytes, str | None, str | None]:
    """
    返回: (content_bytes, mime, suggested_name)
    支持:
      - {"image_url": {"url": "http(s)://..."}}
      - {"image_url": {"url": "data:...;base64,...."}}
      - {"image_url": {"url": "<pure base64>"}}
    也兼容:
      - file.get("filename") / file.get("name")
    """
    file_content = (file.get("image_url", {}) or {}).get("url", "") or ""
    suggested_name = file.get("filename") or file.get("name")

    if file_content.startswith(("http://", "https://")):
        return None, None, suggested_name  # 让调用方去下载并再做后缀处理

    _DATA_URL_RE = re.compile(
        r"^data:(?P<mime>[-\w.+/]+)?(?:;charset=[-\w]+)?;base64,(?P<data>.+)$",
        re.IGNORECASE | re.DOTALL,
    )

    m = _DATA_URL_RE.match(file_content)
    if m:
        mime = m.group("mime") or None
        encoded = m.group("data")
        try:
            content = base64.b64decode(encoded, validate=True)
        except binascii.Error:
            # 有些 data url 会包含换行/空格等
            content = base64.b64decode(encoded)
        return content, mime, suggested_name

    # 纯 base64
    encoded = file_content
    try:
        content = base64.b64decode(encoded, validate=True)
    except binascii.Error:
        content = base64.b64decode(encoded)
    return content, None, suggested_name

def _build_claude_command(
        user_prompt: str,
        session_id: str = "",
        system_prompt: Optional[str] = None,
        output_format: str = "stream-json",
        is_plan_mode: bool = False,
) -> str:
    """
    构建 Claude 命令行

    Args:
        user_prompt: 用户提示词
        llm_model: LLM 模型名称
        session_id: 会话 ID（可选）
        system_prompt: 系统提示词（可选）
        output_format: 输出格式 (json/stream-json)
        is_plan_mode: 是否开启plan模式

    Returns:
        完整的命令字符串
    """

    # 构建命令列表（使用列表而不是字符串拼接）
    command_parts = []

    # 使用 printf 而不是 echo，更好地处理特殊字符
    # 或者使用 here-document 方式
    # 如果是plan模式，需要关掉--dangerously-skip-permissions
    if is_plan_mode:
        command_parts.extend([
            "printf", "%s", shlex.quote(user_prompt),
            "|", "claude", "-p",
            "--permission-mode", "plan",
            "--output-format", shlex.quote(output_format),
            "--verbose"
        ])
    else:
        command_parts.extend([
            "printf", "%s", shlex.quote(user_prompt),
            "|", "claude", "-p",
            "--dangerously-skip-permissions", "true",
            "--output-format", shlex.quote(output_format),
            "--verbose"
        ])

    if output_format == "stream-json":
        command_parts.append("--include-partial-messages")

    if session_id and session_id.strip():
        command_parts.extend(["--resume", shlex.quote(session_id)])

    if system_prompt and system_prompt.strip():
        command_parts.extend(["--system-prompt", shlex.quote(system_prompt)])

    return " ".join(command_parts)

async def _save_attachments(files, workspace_path):
    attachment_path = f"{workspace_path}/.302ai/attachments"
    os.makedirs(attachment_path, exist_ok=True)

    saved = []
    if not files:
        return saved

    for idx, file in enumerate(files):
        try:
            file_content = (file.get("image_url", {}) or {}).get("url", "") or ""
            suggested_name = file.get("filename") or file.get("name")

            if file_content.startswith(("http://", "https://")):
                # 从 URL 下载
                content = await download_file_from_url(file_content)
                # 尝试用 URL 路径名做文件名
                path_name = os.path.basename(urlparse(file_content).path) or None
                base = _safe_filename(os.path.splitext(path_name or suggested_name or f"file_{idx}")[0])
                ext = os.path.splitext(path_name or "")[1]
                if not ext:
                    ext = _guess_ext(content, None)
                filename = base + ext
            else:
                # base64 / data url
                content, mime, suggested_name2 = _parse_file_item(file)
                base = _safe_filename(os.path.splitext(suggested_name2 or f"file_{idx}")[0])
                ext = os.path.splitext(suggested_name2 or "")[1] or _guess_ext(content, mime)
                filename = base + ext

            full_path = os.path.join(attachment_path, filename)

            # 避免重名覆盖：自动加后缀
            if os.path.exists(full_path):
                stem, ext2 = os.path.splitext(filename)
                full_path = os.path.join(attachment_path, f"{stem}_{uuid.uuid4().hex[:8]}{ext2}")

            with open(full_path, "wb") as f:
                f.write(content)

            saved.append(full_path)

        except Exception as e:
            return

    return saved

# 用于识别手动插入数据的固定前缀
MANUAL_INSERT_PREFIX = "阅读这个skill相关信息， 并只回复我已经阅读完毕"


def _split_concatenated_json_objects(s: str) -> list[Any]:
    """
    从一段文本中顺序解析出多个 JSON 对象。
    不依赖换行；即使 JSON 字符串值里包含真实换行也能工作。
    """
    dec = json.JSONDecoder()
    i = 0
    n = len(s)
    out = []

    while True:
        while i < n and s[i].isspace():
            i += 1
        if i >= n:
            break

        obj, j = dec.raw_decode(s, i)
        out.append(obj)
        i = j

    return out


def _is_manual_inserted_record(record: dict) -> bool:
    """
    判断记录是否为手动插入的数据

    Args:
        record: JSONL记录

    Returns:
        True 如果是手动插入的记录
    """
    if record.get("type") != "user":
        return False

    message = record.get("message", {})
    if message.get("role") != "user":
        return False

    content = message.get("content", "")

    # 检查是否以固定前缀开头
    if isinstance(content, str) and content.startswith(MANUAL_INSERT_PREFIX):
        return True

    # 检查是否是配对的"我已经阅读完毕"回复
    if content == "我已经阅读完毕":
        return True

    return False


def _remove_manual_inserted_records(records: list[dict]) -> tuple[list[dict], int]:
    """
    移除手动插入的记录，并修复 parentUuid 链

    Args:
        records: 原始记录列表

    Returns:
        (清理后的记录列表, 移除的记录数量)
    """
    if not records:
        return records, 0

    # 构建 uuid -> record 的映射
    uuid_to_record = {r.get("uuid"): r for r in records if r.get("uuid")}

    # 标记需要移除的记录
    removed_uuids = set()

    # 标记所有手动插入的记录
    for record in records:
        if _is_manual_inserted_record(record):
            removed_uuids.add(record.get("uuid"))

    if not removed_uuids:
        return records, 0

    # 找到每个被删除节点的有效父节点
    def find_valid_parent(uuid_val: str) -> Optional[str]:
        """向上查找第一个未被删除的父节点"""
        current = uuid_val
        visited = set()
        while current and current not in visited:
            visited.add(current)
            if current not in removed_uuids:
                return current
            record = uuid_to_record.get(current)
            if record:
                current = record.get("parentUuid")
            else:
                break
        return None

    # 过滤并修复记录
    cleaned_records = []
    for record in records:
        record_uuid = record.get("uuid")

        # 跳过被标记删除的记录
        if record_uuid in removed_uuids:
            continue

        # 检查是否需要修复 parentUuid
        parent_uuid = record.get("parentUuid")
        if parent_uuid and parent_uuid in removed_uuids:
            valid_parent = find_valid_parent(parent_uuid)
            if valid_parent:
                record = record.copy()
                record["parentUuid"] = valid_parent

        cleaned_records.append(record)

    return cleaned_records, len(removed_uuids)


def _records_to_jsonl(records: list[dict]) -> str:
    """
    将记录列表转换为 JSONL 字符串
    """
    lines = [json.dumps(record, ensure_ascii=False) for record in records]
    return '\n'.join(lines) + '\n' if lines else ''


def _find_folder_upto_depth2(root_dir: Union[str, Path], target_name: str) -> List[str]:
    """
    在 root_dir 下查找名为 target_name 的文件夹，深度 <= 2：
      - 深度0：root_dir 本身
      - 深度1：root_dir 的直接子目录
      - 深度2：root_dir 的子子目录
    返回所有命中的完整路径（字符串）。
    """
    root = Path(root_dir)
    results: List[str] = []

    if not root.is_dir():
        return results

    # 深度0
    if root.name == target_name:
        results.append(str(root.resolve()))

    # 深度1、2
    for d1 in root.iterdir():
        if not d1.is_dir():
            continue

        if d1.name == target_name:
            results.append(str(d1.resolve()))

        for d2 in d1.iterdir():
            if d2.is_dir() and d2.name == target_name:
                results.append(str(d2.resolve()))

    return results


def _generate_qa_batch_content(
        file_content: str,
        qa_list: list[tuple[str, str]],
        auto_clean: bool = True
) -> Optional[dict]:
    """
    根据现有JSONL内容和问答列表，生成需要追加的内容

    会自动检测并移除之前手动插入的数据（以固定前缀开头的记录）

    Args:
        file_content: 现有JSONL文件的内容字符串
        qa_list: 问答对列表，每个元素为 (question, answer) 元组
        auto_clean: 是否自动清理之前手动插入的数据，默认True

    Returns:
        包含以下字段的字典:
        - append_content: 需要追加到文件的内容字符串
        - count: 问答对数量
        - records: 生成的所有记录
        - first_user_uuid: 第一条用户记录的UUID
        - last_assistant_uuid: 最后一条助手记录的UUID
        - full_content: 完整的文件内容（始终有值，可直接用于重写文件）
        - cleaned_content: 清理后的完整文件内容（需要重写时使用，否则为None）
        - removed_count: 移除的旧记录数量
        - needs_rewrite: 是否需要重写整个文件（而非追加）
        如果解析失败则返回None
    """
    if not qa_list:
        return None

    # 解析文件内容
    try:
        records = _split_concatenated_json_objects(file_content)
    except json.JSONDecodeError:
        traceback.print_exc()
        return None

    if not records:
        return None

    # 清理手动插入的数据
    removed_count = 0
    needs_rewrite = False

    if auto_clean:
        records, removed_count = _remove_manual_inserted_records(records)
        needs_rewrite = removed_count > 0
        if removed_count > 0:
            print(f"已移除 {removed_count} 条手动插入的记录")

    # 从后往前查找所需字段
    parent_uuid = None
    session_id = None
    cwd = None
    version = None
    git_branch = None
    user_type = None

    for record in reversed(records):
        if not parent_uuid and record.get('uuid'):
            parent_uuid = record['uuid']
        if not session_id and record.get('sessionId'):
            session_id = record['sessionId']
        if not cwd and record.get('cwd'):
            cwd = record['cwd']
        if not version and record.get('version'):
            version = record['version']
        if git_branch is None and 'gitBranch' in record:
            git_branch = record['gitBranch']
        if not user_type and record.get('userType'):
            user_type = record['userType']
        if all([parent_uuid, session_id, cwd, version, git_branch is not None, user_type]):
            break

    if not all([parent_uuid, session_id, cwd, version, user_type]):
        return None

    # 生成所有记录
    all_records = []
    current_parent_uuid = parent_uuid

    for question, answer in qa_list:
        user_uuid = str(uuid.uuid4())
        user_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        user_record = {
            "parentUuid": current_parent_uuid,
            "isSidechain": False,
            "userType": user_type,
            "cwd": cwd,
            "sessionId": session_id,
            "version": version,
            "gitBranch": git_branch or "",
            "type": "user",
            "message": {"role": "user", "content": question + answer},
            "uuid": user_uuid,
            "timestamp": user_time
        }

        assistant_uuid = str(uuid.uuid4())
        assistant_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        assistant_record = {
            "parentUuid": user_uuid,
            "isSidechain": False,
            "userType": user_type,
            "cwd": cwd,
            "sessionId": session_id,
            "version": version,
            "gitBranch": git_branch or "",
            "type": "user",
            "message": {"role": "user", "content": "我已经阅读完毕"},
            "uuid": assistant_uuid,
            "timestamp": assistant_time
        }

        all_records.append({"user": user_record, "assistant": assistant_record})
        current_parent_uuid = assistant_uuid

    # 生成追加内容字符串
    new_lines = []
    for record in all_records:
        new_lines.append(json.dumps(record["user"], ensure_ascii=False))
        new_lines.append(json.dumps(record["assistant"], ensure_ascii=False))
    append_content = '\n'.join(new_lines) + '\n'

    # 生成完整内容
    if needs_rewrite:
        # 清理后的记录 + 新内容
        base_content = _records_to_jsonl(records)
        full_content = base_content + append_content
        cleaned_content = full_content
    else:
        # 原内容 + 新内容
        base_content = file_content.rstrip('\n') + '\n' if file_content.strip() else ''
        full_content = base_content + append_content
        cleaned_content = None

    return {
        "append_content": append_content,
        "count": len(qa_list),
        "records": all_records,
        "first_user_uuid": all_records[0]["user"]["uuid"],
        "last_assistant_uuid": all_records[-1]["assistant"]["uuid"],
        "full_content": full_content,
        "cleaned_content": cleaned_content,
        "removed_count": removed_count,
        "needs_rewrite": needs_rewrite
    }


