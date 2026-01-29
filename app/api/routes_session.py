from __future__ import annotations


import math
import os
import secrets
import shutil
import string

from fastapi import APIRouter, Depends, Request, Query
from app.api.response import fail, ok
from app.core.config import ROOT_SAVE_PATH
from app.db.session import get_db, run_in_threadpool
from app.repositories.session_repo import SessionRepository


from pydantic import BaseModel, Field

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


class ProjectInitRequest(BaseModel):

    session_id: str = Field(..., description="实际是session_alias, 对外暴露成session_id，让用户接触不到真正的cc session_id")
    workspace_path: str = Field(..., description="工作区路径")


class SessionUpdateRequest(BaseModel):

    session_id: str = Field(..., description="实际是session_alias, 对外暴露成session_id，让用户接触不到真正的cc session_id")
    note: str = Field(..., description="session note")
    sandbox_id: str = Field(None, description="兼容在线版本的接口，没有实际意义")


class SessionDeleteRequest(BaseModel):

    session_id: str = Field(..., description="实际是session_alias, 对外暴露成session_id，让用户接触不到真正的cc session_id")


def get_session_repo(db=Depends(get_db)) -> SessionRepository:
    return SessionRepository(db)


@router.post("/project/init")
async def init_project(payload: ProjectInitRequest, repo: SessionRepository = Depends(get_session_repo)):
    workspace_path = f"{ROOT_SAVE_PATH}/workspace/{_secure_rand_str()}" if not payload.workspace_path else payload.workspace_path

    def op():
        if repo.get_session_by_alias(payload.session_id) is not None:
            return False, "session already exist"



        repo.create_session(
            session_alias=payload.session_id,
            workspace_path=workspace_path,
        )
        return True, "session created"

    is_success, msg = await run_in_threadpool(op)
    if not is_success:
        return fail(msg, status_code=400)
    os.makedirs(workspace_path, exist_ok=True)
    return ok({"workspace_path": workspace_path, "session_id": payload.session_id, "message": "Initialization succeeded"})


@router.get("/session")
async def get_session(limit: int = Query(50, description="每页数量"),
                      offset: int = Query(0, description="偏移量"),
                      sandbox_id: str = Query("", description="沙盒id，为了跟在线接口一致，在本地接口没有意义"),
                      repo: SessionRepository = Depends(get_session_repo)):
    def op():
        return repo.list_sessions(limit=limit, offset=offset)

    result = await run_in_threadpool(op)

    items = [{"session_id": x.session_alias, "note": x.note, "workspace_path": x.workspace_path} for x in result.items]
    total = result.total

    # total_pages = math.ceil(total / limit) if limit > 0 else 0

    return ok({"session_list": items, "sandbox_id": sandbox_id})

@router.post("/session")
async def update_session(payload: SessionUpdateRequest, repo: SessionRepository = Depends(get_session_repo)):

    def op():
        session = repo.get_session_by_alias(payload.session_id)
        if session is None:
            return False, "session does not exist"
        repo.update_session(session.id, note=payload.note)
        return True, "session updated"

    is_success, msg = await run_in_threadpool(op)
    if not is_success:
        return fail(msg, status_code=404)
    return ok({"note": payload.note, "message": msg, "session_id": payload.session_id, "sandbox_id": payload.sandbox_id or ""})


@router.delete("/session")
async def delete_session(payload: SessionDeleteRequest, repo: SessionRepository = Depends(get_session_repo)):
    def op():
        session = repo.get_session_by_alias(payload.session_id)
        if session is None:
            return False, "session does not exist"
        repo.delete_session(session.id)
        return True, session.workspace_path

    is_success, msg = await run_in_threadpool(op)
    if not is_success:
        return fail(msg, status_code=404)
    shutil.rmtree(msg, ignore_errors=True)

    return ok({"message": "session deleted"})


@router.post("/create")
async def test_create_sandbox():
    return ok({"data": {
        "sandbox_id": "302-sandbox-123456",
        "sandbox_name": "xxxxxxxxxxx"
    }})

@router.get("/list")
async def test_list_sandbox(repo: SessionRepository = Depends(get_session_repo)):

    def op():
        return repo.list_sessions()

    result = await run_in_threadpool(op)

    items = [{"session_id": x.session_alias, "note": x.note, "workspace_path": x.workspace_path} for x in result.items]

    return ok({
        "pagination": {
            "current_page": 1,
            "page_size": 50,
            "total_items": 1,
            "total_pages": 1
        },
        "list": [
            {
                "sandbox_id": "302-sandbox-123456",
                "status": "paused",
                "sandbox_name": "",
                "llm_model": "claude-opus-4-5-20251101",
                "max_thinking_token": 2048,
                "disk_used": 0,
                "disk_total": 0,
                "session_num": 0,
                "created_at": "2025-12-01T02:15:55.186331Z",
                "updated_at": "2025-12-01T02:18:13.660241Z",
                "deleted_at": "",
                "session_list": items
            }
        ]
    })

def _secure_rand_str(n=10):
    alphabet = string.ascii_lowercase + string.digits  # a-z + 0-9
    return ''.join(secrets.choice(alphabet) for _ in range(n))