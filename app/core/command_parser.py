import re
import json
import shlex
from typing import Optional, Dict, Any, Union
from pydantic import BaseModel, Field, validator
from enum import Enum
import asyncio


class CommandType(Enum):
    """命令类型枚举"""
    COMMAND = "command"
    MODEL = "model"
    DEPLOY = "deploy"
    MAX_THINKING_TOKEN = "max_thinking_token"
    PLUGIN = "plugin"  # ✅ 新增
    UNKNOWN = "unknown"


class SandboxCommandParams(BaseModel):
    user: str = "user"
    command: str
    request_time: float = None
    envs: Dict[str, str] = None
    cwd: str = None


class ModelParams(BaseModel):
    model_name: str


class DeployParams(BaseModel):
    session_id: str
    envs: Dict[str, str] = None
    vercel_key: str = None
    project_name: str = None


class PluginParams(BaseModel):
    """ /plugin 指令参数（仅支持 /plugin XXXX）"""
    plugin_args: str


class MaxThinkingTokenParams(BaseModel):
    """max_thinking_token 指令参数"""
    value: int = Field(..., ge=0, description="思考token的最大值，必须为非负整数（0或正整数）")

    @validator('value')
    def validate_value(cls, v):
        if v < 0:
            raise ValueError("max_thinking_token value must be non-negative (0 or positive)")
        return v


class ParsedCommand(BaseModel):
    """统一的命令解析结果"""
    command_type: CommandType
    data: Union[SandboxCommandParams, ModelParams, DeployParams, MaxThinkingTokenParams, PluginParams, None]
    raw_message: str


async def parse_command_from_message(
        message: str,
        header_params: Optional[Dict[str, Any]] = None
) -> Optional[ParsedCommand]:
    """
    异步解析多种类型的命令指令

    支持的命令格式:
    1. /commands "df -h"
    2. /commands --command "df -h" --user "admin" --envs '{"PATH": "/usr/bin"}'
    3. /model gpt-4
    4. /deploy session_123
    5. /deploy --session_id "session_123" --envs '{"ENV": "prod"}'
    6. /max_thinking_token 1000
    7. /max_thinking_token --value 2000

    Args:
        message: 输入的消息字符串
        header_params: 从请求头提取的参数字典(可选)

    Returns:
        ParsedCommand对象或None
    """
    if not message or not message.strip():
        return None

    message = message.strip()
    header_params = header_params or {}

    # 判断命令类型并异步解析
    if message.startswith('/commands'):
        return await _parse_commands(message, header_params)
    elif message.startswith('/model'):
        return await _parse_model(message, header_params)
    elif message.startswith('/deploy'):
        return await _parse_deploy(message, header_params)
    elif message.startswith('/max_thinking_token'):
        return await _parse_max_thinking_token(message, header_params)
    elif message.startswith('/plugin'):
        return await _parse_plugin(message, header_params)
    else:
        return None


async def _parse_plugin(message: str, header_params: Dict[str, Any]) -> Optional[ParsedCommand]:
    """仅支持：/plugin XXXX"""
    content = message[7:].strip()  # 移除 '/plugin'

    if not content:
        return None

    # 不做复杂参数解析，保留用户输入原样（去掉首尾引号）
    plugin_args = content.strip().strip('\'"')
    if not plugin_args:
        return None

    return ParsedCommand(
        command_type=CommandType.PLUGIN,
        data=PluginParams(plugin_args=plugin_args),
        raw_message=message
    )


async def _parse_commands(message: str, header_params: Dict[str, Any]) -> Optional[ParsedCommand]:
    """异步解析 /commands 指令"""
    content = message[9:].strip()  # 移除 '/commands'

    # 初始化参数(从header_params获取默认值)
    params = {
        "command": header_params.get("command"),
        "user": header_params.get("user", "user"),
        "envs": header_params.get("envs"),
        "cwd": header_params.get("cwd"),
        "request_time": header_params.get("request_time")
    }

    try:
        # 简单模式:直接跟命令
        if not content.startswith('--'):
            if content:
                command = content.strip('\'"')
                if command:
                    params["command"] = command  # 指令中的command优先

            if not params["command"]:
                return None

            # 过滤None值
            params = {k: v for k, v in params.items() if v is not None}

            return ParsedCommand(
                command_type=CommandType.COMMAND,
                data=SandboxCommandParams(**params),
                raw_message=message
            )

        # 复杂模式:使用参数
        tokens = shlex.split(content)

        i = 0
        while i < len(tokens):
            if tokens[i].startswith('--') and i + 1 < len(tokens):
                key = tokens[i][2:]
                value = tokens[i + 1]

                if key in params:
                    if key == 'envs':
                        # 指令中的envs优先,可以考虑合并
                        parsed_envs = json.loads(value)
                        if params.get('envs'):
                            # 合并envs,指令中的优先
                            params[key] = {**params['envs'], **parsed_envs}
                        else:
                            params[key] = parsed_envs
                    elif key == 'request_time':
                        params[key] = float(value)
                    else:
                        params[key] = value  # 指令参数覆盖header参数
                i += 2
            else:
                i += 1

        if not params["command"]:
            return None

        # 过滤None值
        params = {k: v for k, v in params.items() if v is not None}

        return ParsedCommand(
            command_type=CommandType.COMMAND,
            data=SandboxCommandParams(**params),
            raw_message=message
        )

    except Exception as e:
        print(f"解析 /commands 指令时出错: {e}")
        return None


async def _parse_model(message: str, header_params: Dict[str, Any]) -> Optional[ParsedCommand]:
    """异步解析 /model 指令"""
    content = message[6:].strip()  # 移除 '/model'

    try:
        model_name = None

        # 优先从指令中获取
        if content:
            model_name = content.strip('\'"')

        # 如果指令中没有,从header_params获取
        if not model_name:
            model_name = header_params.get("model_name")

        if not model_name:
            return None

        return ParsedCommand(
            command_type=CommandType.MODEL,
            data=ModelParams(model_name=model_name),
            raw_message=message
        )

    except Exception as e:
        print(f"解析 /model 指令时出错: {e}")
        return None


async def _parse_deploy(message: str, header_params: Dict[str, Any]) -> Optional[ParsedCommand]:
    """异步解析 /deploy 指令"""
    content = message[7:].strip()  # 移除 '/deploy'

    # 初始化参数(从header_params获取默认值)
    params = {
        "session_id": header_params.get("session_id"),
        "envs": header_params.get("envs"),
        "vercel_key": header_params.get("vercel_key"),
        "project_name": header_params.get("project_name"),
    }

    try:
        # 简单模式: 直接跟 session_id
        if not content.startswith('--'):
            if content:
                session_id = content.strip('\'"')
                if session_id:
                    params["session_id"] = session_id  # 指令中的session_id优先

            if not params["session_id"]:
                return None

            params = {k: v for k, v in params.items() if v is not None}

            return ParsedCommand(
                command_type=CommandType.DEPLOY,
                data=DeployParams(**params),
                raw_message=message
            )

        # 复杂模式: 使用参数
        tokens = shlex.split(content)

        i = 0
        while i < len(tokens):
            if tokens[i].startswith('--') and i + 1 < len(tokens):
                key = tokens[i][2:]
                value = tokens[i + 1]

                if key in params:
                    if key == 'envs':
                        parsed_envs = json.loads(value)
                        if params.get('envs'):
                            params[key] = {**params['envs'], **parsed_envs}  # 指令优先
                        else:
                            params[key] = parsed_envs
                    else:
                        params[key] = value  # 指令参数覆盖header参数
                i += 2
            else:
                i += 1

        if not params["session_id"]:
            return None

        params = {k: v for k, v in params.items() if v is not None}

        return ParsedCommand(
            command_type=CommandType.DEPLOY,
            data=DeployParams(**params),
            raw_message=message
        )

    except Exception as e:
        print(f"解析 /deploy 指令时出错: {e}")
        return None



async def _parse_max_thinking_token(message: str, header_params: Dict[str, Any]) -> Optional[ParsedCommand]:
    """
    异步解析 /max_thinking_token 指令

    支持格式:
    - /max_thinking_token 0
    - /max_thinking_token 1000
    - /max_thinking_token --value 2000
    """
    content = message[19:].strip()  # 移除 '/max_thinking_token'

    try:
        value = None

        # 简单模式:直接跟数值
        if not content.startswith('--'):
            if content:
                # 尝试解析数值
                try:
                    value = int(content.strip('\'"'))
                except ValueError:
                    print(f"无效的数值: {content}")
                    return None
        else:
            # 复杂模式:使用 --value 参数
            tokens = shlex.split(content)
            i = 0
            while i < len(tokens):
                if tokens[i] == '--value' and i + 1 < len(tokens):
                    try:
                        value = int(tokens[i + 1])
                    except ValueError:
                        print(f"无效的数值: {tokens[i + 1]}")
                        return None
                    break
                i += 1

        # 如果指令中没有值，尝试从header_params获取
        if value is None:
            value = header_params.get("max_thinking_token")
            if value is not None:
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    print(f"header中的max_thinking_token值无效: {value}")
                    return None

        if value is None:
            print("max_thinking_token 指令需要提供数值")
            return None

        # 验证值的有效性（允许0和正整数）
        if value < 0:
            print(f"max_thinking_token 值必须为非负整数（0或正整数），当前值: {value}")
            return None

        return ParsedCommand(
            command_type=CommandType.MAX_THINKING_TOKEN,
            data=MaxThinkingTokenParams(value=value),
            raw_message=message
        )

    except Exception as e:
        print(f"解析 /max_thinking_token 指令时出错: {e}")
        return None


# 便捷函数:直接获取特定类型的数据
async def get_command_request(
        message: str,
        header_params: Optional[Dict[str, Any]] = None
) -> Optional[SandboxCommandParams]:
    """异步获取 SandboxCommandRequest"""
    result = await parse_command_from_message(message, header_params)
    if result and result.command_type == CommandType.COMMAND:
        return result.data
    return None


async def get_model_request(
        message: str,
        header_params: Optional[Dict[str, Any]] = None
) -> Optional[ModelParams]:
    """异步获取 ModelRequest"""
    result = await parse_command_from_message(message, header_params)
    if result and result.command_type == CommandType.MODEL:
        return result.data
    return None


async def get_deploy_request(
        message: str,
        header_params: Optional[Dict[str, Any]] = None
) -> Optional[DeployParams]:
    """异步获取 DeployRequest"""
    result = await parse_command_from_message(message, header_params)
    if result and result.command_type == CommandType.DEPLOY:
        return result.data
    return None


async def get_max_thinking_token_request(
        message: str,
        header_params: Optional[Dict[str, Any]] = None
) -> Optional[MaxThinkingTokenParams]:
    """异步获取 MaxThinkingTokenRequest"""
    result = await parse_command_from_message(message, header_params)
    if result and result.command_type == CommandType.MAX_THINKING_TOKEN:
        return result.data
    return None


# 批量解析函数(利用异步优势)
async def parse_commands_batch(
        messages: list[str],
        header_params: Optional[Dict[str, Any]] = None
) -> list[Optional[ParsedCommand]]:
    """
    批量异步解析多条消息

    Args:
        messages: 消息列表
        header_params: 从请求头提取的参数字典(可选)

    Returns:
        解析结果列表
    """
    tasks = [parse_command_from_message(msg, header_params) for msg in messages]
    return await asyncio.gather(*tasks)


# 测试用例
async def test_async_parser():
    test_cases = [
        # commands 测试
        ('/commands "df -h"', None),
        ("/commands 'ls -la'", None),
        ('/commands --command "df -h" --user "admin"', None),
        ('/commands --command "ls" --user "root" --envs \'{"PATH": "/usr/bin"}\' --cwd "/home"', None),

        # 从header获取command
        ('/commands --user "admin"', {"command": "ps aux"}),
        ('/commands', {"command": "top", "user": "root"}),

        # model 测试
        ('/model gpt-4', None),
        ('/model "claude-3-opus"', None),
        ("/model 'gemini-pro'", None),

        # 从header获取model
        ('/model', {"model_name": "gpt-4-turbo"}),

        # deploy 测试
        ('/deploy session_123', None),
        ('/deploy "session_456"', None),
        ('/deploy --session_id "session_789"', None),
        ('/deploy --session_id "session_abc" --envs \'{"ENV": "prod", "REGION": "us-east-1"}\'', None),

        # 从header获取session_id
        ('/deploy', {"session_id": "session_from_header"}),
        ('/deploy --envs \'{"ENV": "prod"}\'', {"session_id": "session_999"}),

        # max_thinking_token 测试 (新增)
        ('/max_thinking_token 1000', None),
        ('/max_thinking_token 5000', None),
        ('/max_thinking_token --value 2000', None),
        ('/max_thinking_token "3000"', None),

        # 从header获取max_thinking_token
        ('/max_thinking_token', {"max_thinking_token": 4000}),
        ('/max_thinking_token', {"max_thinking_token": "6000"}),

        # 无效的max_thinking_token测试
        ('/max_thinking_token', None),  # 没有值
        ('/max_thinking_token 0', None),  # 零值
        ('/max_thinking_token -100', None),  # 负值
        ('/max_thinking_token abc', None),  # 非数字

        # 指令优先级测试
        ('/deploy session_override', {"session_id": "session_from_header"}),
        ('/commands "ls"', {"command": "ps", "user": "admin"}),
        ('/max_thinking_token 8000', {"max_thinking_token": 1000}),

        # 无效测试
        ('normal message', None),
        ('/command "df -h"', None),
        ('/commands', None),
        ('/model', None),
        ('/deploy', None),
    ]

    print("=" * 80)
    print("单个解析测试:")
    for test, headers in test_cases:
        print(f"\n输入: {test}")
        if headers:
            print(f"Header参数: {headers}")
        result = await parse_command_from_message(test, headers)
        if result:
            print(f"命令类型: {result.command_type.value}")
            print(f"解析数据: {result.data.model_dump() if result.data else None}")
        else:
            print("解析结果: None")
        print("-" * 80)

    # 测试便捷函数
    print("\n" + "=" * 80)
    print("测试便捷函数:")
    cmd_req = await get_command_request('/commands "ls -la"')
    print(f"\nget_command_request: {cmd_req}")

    model_req = await get_model_request('/model gpt-4')
    print(f"get_model_request: {model_req}")

    deploy_req = await get_deploy_request('/deploy session_123')
    print(f"get_deploy_request: {deploy_req}")

    # 测试新增的max_thinking_token便捷函数
    max_token_req = await get_max_thinking_token_request('/max_thinking_token 5000')
    print(f"get_max_thinking_token_request: {max_token_req}")

    # 测试header参数
    deploy_req_header = await get_deploy_request('/deploy', {"session_id": "header_session"})
    print(f"get_deploy_request (with header): {deploy_req_header}")

    max_token_req_header = await get_max_thinking_token_request('/max_thinking_token', {"max_thinking_token": 3000})
    print(f"get_max_thinking_token_request (with header): {max_token_req_header}")

    # 测试批量解析
    print("\n" + "=" * 80)
    print("批量解析测试:")
    batch_messages = [
        '/model gpt-4',
        '/commands "ls"',
        '/deploy session_999',
        '/max_thinking_token 2000',
    ]
    results = await parse_commands_batch(batch_messages)
    for msg, result in zip(batch_messages, results):
        print(f"{msg} -> {result.command_type.value if result else 'None'}")

    # 测试批量解析with header
    print("\n批量解析测试(with header):")
    batch_messages_header = [
        '/model',
        '/commands',
        '/deploy',
        '/max_thinking_token',
    ]
    header_params = {
        "model_name": "gpt-4",
        "command": "df -h",
        "session_id": "batch_session",
        "max_thinking_token": 1500
    }
    results_header = await parse_commands_batch(batch_messages_header, header_params)
    for msg, result in zip(batch_messages_header, results_header):
        if result:
            print(f"{msg} -> {result.command_type.value}: {result.data.model_dump() if result.data else None}")
        else:
            print(f"{msg} -> None")


if __name__ == "__main__":
    # Python 3.7+
    asyncio.run(test_async_parser())

    # 或者使用传统方式
    # loop = asyncio.get_event_loop()
    # loop.run_until_complete(test_async_parser())
