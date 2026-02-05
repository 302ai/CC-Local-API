from __future__ import annotations

from fastapi import APIRouter

from app.api.routes_common import router as common_router
from app.api.routes_command import router as command_router
from app.api.routes_file import router as file_router
from app.api.routes_skill import router as skill_router
from app.api.routes_chat import router as chat_router
from app.api.routes_session import router as session_router
from app.api.routes_mcp import router as mcp_router

SANDBOX_PREFIX = "/302/claude-code/sandbox"
CC_PREFIX = "/302/claude-code"

CHAT_PREFIX = "/api/v1"


sandbox_router = APIRouter(prefix=SANDBOX_PREFIX, tags=["Sandbox"])

# base_router = APIRouter()

cc_router = APIRouter(prefix=CC_PREFIX, tags=["Base"])

chat_base_router = APIRouter(prefix=CHAT_PREFIX, tags=["Chat"])

sandbox_router.include_router(common_router)
cc_router.include_router(command_router)
sandbox_router.include_router(file_router)
chat_base_router.include_router(chat_router)
sandbox_router.include_router(session_router)

sandbox_router.include_router(mcp_router)


cc_router.include_router(skill_router)
