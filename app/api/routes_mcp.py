from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Union

from fastapi import APIRouter

from app.api.response import fail, ok
from app.core.command_runner import CommandRunner
from app.core.file_content import read_file_as_text_async
from app.core.log import log_error, log_info, log_warning

from pydantic import BaseModel, Field

router = APIRouter()

class MCPAddRequest(BaseModel):
    sandbox_id: str = Field(None, description="跟在线接口保持一致，在本地接口这个字段没实际意义")
    mcp_servers: Union[str, List] = Field(
        ...,
        description="MCP服务器配置，可以是字符串或列表"
    )
    auto_purging: bool = Field(True, description="是否清楚之前安装的MCP")


@router.post("/mcp/add", description="添加全局的MCP")
async def add_mcp(payload: MCPAddRequest):
    # 验证MCP命令格式
    mcp_list = payload.mcp_servers if isinstance(payload.mcp_servers, list) else [payload.mcp_servers]
    for mcp in mcp_list:
        if not mcp.startswith("claude mcp add"):
            return fail("mcp_servers must start with 'claude mcp add'")

    runner = CommandRunner()

    if payload.auto_purging:
        existing_mcp_names = await _get_existing_mcp_servers()
        if existing_mcp_names:
            log_info(f"Found existing MCP servers: {existing_mcp_names}")
            for mcp_name in existing_mcp_names:
                del_mcp_result = await runner.exec_json(f"claude mcp remove {mcp_name}")
                if del_mcp_result.exit_code != 0:
                    log_error(f"Failed to remove {mcp_name}")
                else:
                    log_info(f"Successfully removed {mcp_name}")

    # 添加新的MCP服务器
    for mcp in mcp_list:
        # 如果没有指定scope，设置为user
        if " --scope" not in mcp:
            mcp += " --scope user"
        add_mcp_result = await runner.exec_json(mcp)
        if add_mcp_result.exit_code != 0:
            return fail(f"Failed to add {mcp}: {add_mcp_result.stderr}")
        log_info(f"successfully added {mcp}")

    resp = {
        "message": "Successfully added MCP",
        "sandbox_id": payload.sandbox_id,
    }
    return ok(resp)



async def _get_existing_mcp_servers() -> list[str]:
    """获取现有的MCP服务器列表"""
    config_path = "/home/user/.claude.json"

    if not os.path.isfile(config_path):
        return []

    try:
        # 读取配置文件
        config_str = await read_file_as_text_async(Path(config_path))
        config_json = json.loads(config_str)

        # 获取MCP服务器名称列表
        mcp_servers = config_json.get("mcpServers", {})
        return list(mcp_servers.keys())
    except (json.JSONDecodeError, Exception) as e:
        log_warning(f"Failed to parse claude config: {e}")
        return []