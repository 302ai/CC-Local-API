from __future__ import annotations

import base64
import os
import shutil
import asyncio

from app.api.request import parse_request_data
from app.core.config import MAX_FILE_SIZE
from app.core.file_content import create_zip_from_directory, read_file_as_base64, read_file_as_text, extract_zip_file
from typing import Any, Optional, Literal, List
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from starlette.datastructures import UploadFile
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.response import fail, ok
from app.core.file_io import download_file_from_url, write_file_async
from app.db.session import run_in_threadpool

router = APIRouter()

# In-process per-file write locks + last seen timestamp.
# Note: if you run multiple workers/processes, this only protects within a process.
_FILE_WRITE_LOCKS: dict[str, asyncio.Lock] = {}
_FILE_LAST_TS: dict[str, int] = {}


def _get_file_lock(key: str) -> asyncio.Lock:
    lock = _FILE_WRITE_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _FILE_WRITE_LOCKS[key] = lock
    return lock


# 文本文件扩展名白名单
TEXT_EXT_WHITELIST = {
    "txt", "md", "json", "xml", "yaml", "yml", "toml", "ini", "cfg", "conf",
    "py", "js", "ts", "jsx", "tsx", "vue", "svelte",
    "html", "htm", "css", "scss", "sass", "less",
    "java", "c", "cpp", "h", "hpp", "cs", "go", "rs", "rb", "php",
    "sh", "bash", "zsh", "fish", "ps1", "bat", "cmd",
    "sql", "graphql", "prisma",
    "env", "env.example", "env.local", "env.development", "env.production",
    "gitignore", "dockerignore", "editorconfig",
    "makefile", "dockerfile", "vagrantfile",
    "csv", "tsv", "log",
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
    ".env",
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


EXCLUDE_EXTENSIONS = {".pyc", ".swp", ".swo", ".log"}


class FileListRequest(BaseModel):
    path: str = Field(..., description="Root path to list")
    depth: int = Field(0, ge=0, le=50, description="Max recursion depth, 0 means only the given path")


class FileDownloadRequest(BaseModel):
    path: str = Field(..., description="Path to download file/dir")
    format: Literal["file", "base64", "text"] = Field("file", description="File format")


class FileUploadItem(BaseModel):
    save_path: str = Field(..., description="File save path")
    content: str = Field(..., description="File content (base64 or URL)")
    ts: int = Field(0, description="Client version timestamp (ms). Newer wins. 0 disables version control.")


class FileBatchUploadRequest(BaseModel):
    file_list: List[FileUploadItem] = Field(..., description="List of files to upload")


class FileCommonOperationRequest(BaseModel):
    operation: Literal["rename", "copy", "move", "remove", "mkdir"] = Field(
        ...,
        description="File Operation type"
    )
    sandbox_id: str = Field("", description="只是兼容在线服务的数据格式，在本地接口上没有实际意义")
    original_path: str = Field(..., description="Original path")
    target_path: str = Field("", description="Target path")


@router.post("/file/list")
async def list_files(payload: FileListRequest):
    def op():
        root = Path(payload.path).expanduser().resolve()
        return _list_entries(root, payload.depth)

    try:
        entries = await run_in_threadpool(op)
    except FileNotFoundError as e:
        return fail("path not found", status_code=404, payload={"path": str(e)})

    return ok({"filelist": entries})


@router.post("/file/download")
async def download_file(payload: FileDownloadRequest):
    """
    下载文件或目录

    - format="file": 返回文件流（目录会被压缩为 zip）
    - format="base64": 返回 base64 编码的内容（目录会被压缩为 zip）
    - format="text": 返回文本内容（仅支持文件，不支持目录）
    """

    # 验证 format 参数
    if payload.format not in ("base64", "file", "text"):
        return fail("invalid format", status_code=400, payload={"detail": "format must be 'base64', 'file', or 'text'"})

    # 验证 path 参数
    if not payload.path:
        return fail("path parameter is required", status_code=400)

    # 解析路径
    file_path = Path(payload.path).expanduser().resolve()

    # 检查路径是否存在
    if not file_path.exists():
        return fail("path not found", status_code=404)

    is_dir = file_path.is_dir()

    # text 格式不支持目录
    if payload.format == "text" and is_dir:
        return fail(
            "invalid format",
            status_code=400,
            payload={"detail": "format 'text' only supports file path; for directory use format 'base64' or 'file'"},
        )

    # text 格式检查文件扩展名
    if payload.format == "text":
        ext = file_path.suffix.lower().lstrip(".")
        # 处理没有扩展名的文件（如 Makefile, Dockerfile）
        if not ext:
            ext = file_path.name.lower()

        if ext not in TEXT_EXT_WHITELIST and file_path.name.lower() not in TEXT_EXT_WHITELIST:
            return fail(
                "unsupported file type",
                status_code=400,
                payload={"detail": f"Unsupported file type in text format output: {ext or file_path.name}"},
            )

    # 处理 base64 格式
    if payload.format == "base64":
        return await _handle_base64_download(file_path, payload.path, is_dir)

    # 处理 text 格式
    elif payload.format == "text":
        return await _handle_text_download(file_path, payload.path)

    # 处理 file 格式（流式下载）
    elif payload.format == "file":
        return await _handle_file_stream_download(file_path, payload.path, is_dir)


@router.post("/file/upload/batch")
async def batch_upload_files(payload: FileBatchUploadRequest):
    """
    批量上传文件到本地

    支持两种内容格式：
    - URL: 以 http:// 或 https:// 开头，会自动下载
    - Base64: data:xxx;base64,xxx 格式或纯 base64 字符串
    """

    if not payload.file_list:
        return fail("file_list parameter is required", status_code=400)

    upload_results = []

    for file_item in payload.file_list:
        try:
            # 解析保存路径
            save_path = Path(file_item.save_path).expanduser().resolve()

            # 安全检查：防止路径遍历攻击（可选，根据需求调整）
            # if not str(save_path).startswith("/allowed/base/path"):
            #     raise ValueError("Invalid save path")

            # 获取文件内容
            if file_item.content.startswith(("http://", "https://")):
                # 从 URL 下载
                try:
                    content = await download_file_from_url(file_item.content)
                except Exception as e:
                    upload_results.append({
                        "success": False,
                        "file": {"save_path": file_item.save_path},
                        "error": f"Failed to download from URL: {str(e)}"
                    })
                    continue
            else:
                # 处理 base64 编码
                try:
                    # 支持 data:xxx;base64,xxx 格式
                    if "," in file_item.content and "base64" in file_item.content.split(",")[0]:
                        _, encoded = file_item.content.split(",", 1)
                    else:
                        # 纯 base64 字符串
                        encoded = file_item.content

                    content = base64.b64decode(encoded)
                except Exception as e:
                    upload_results.append({
                        "success": False,
                        "file": {"save_path": file_item.save_path},
                        "error": f"Invalid base64 format: {str(e)}"
                    })
                    continue

            lock_key = str(save_path)
            lock = _get_file_lock(lock_key)

            # 写入文件（使用 aiofiles 异步写入）
            async with lock:
                last_ts = _FILE_LAST_TS.get(lock_key, -1)
                if file_item.ts > 0 and file_item.ts <= last_ts:
                    upload_results.append({
                        "success": True,
                        "skipped": True,
                        "reason": f"stale update: ts={file_item.ts} <= last_ts={last_ts}",
                        "file": {"save_path": file_item.save_path},
                    })
                    continue

                await write_file_async(save_path, content)
                if file_item.ts > 0:
                    _FILE_LAST_TS[lock_key] = file_item.ts

            upload_results.append({
                "success": True,
                "file": {
                    "save_path": file_item.save_path,
                    "size": len(content)
                }
            })

        except PermissionError:
            upload_results.append({
                "success": False,
                "file": {"save_path": file_item.save_path},
                "error": "Permission denied"
            })
        except Exception as e:
            upload_results.append({
                "success": False,
                "file": {"save_path": file_item.save_path},
                "error": str(e)
            })

    return ok({"result": upload_results})


@router.post("/file/upload")
async def upload_file(request: Request):
    """
    上传单个文件到本地

    支持的请求格式：
    1. multipart/form-data: 直接上传文件
    2. JSON:
       - file: base64 编码的文件内容 或 URL
       - path: 保存路径
       - auto_unzip: 是否自动解压 zip 文件 (可选)

    参数：
    - file: 文件内容（UploadFile / base64 / URL）
    - path: 保存路径
    - auto_unzip: 是否自动解压 zip 文件（"1", "true", "t" 为真）
    """

    # 检查请求体大小
    content_length = request.headers.get('content-length')
    if content_length and int(content_length) > MAX_FILE_SIZE:
        return fail(f"Request body too large. Maximum size is 20MB, got {int(content_length) / 1024 / 1024:.2f}MB", status_code=413)

    # 解析请求数据
    body = await parse_request_data(request)
    # 参数验证
    file = body.get("file", "")
    path = body.get("path", "")
    auto_unzip = str(body.get("auto_unzip", "")).lower() in ["1", "true", "t"]
    if not file:
        return fail("file parameter is required", status_code=400)
    if not path:
        return fail("path is required", status_code=400)

    # 解析保存路径
    save_path = Path(path).expanduser().resolve()

    # 处理文件内容
    if isinstance(file, UploadFile):
        # multipart/form-data 上传的文件
        content = await file.read()
        original_filename = file.filename or save_path.name
    elif isinstance(file, str):
        if file.startswith(("http://", "https://")):
            # URL 下载
            try:
                content = await download_file_from_url(file)
            except Exception as e:
                return fail(f"Failed to download file: {str(e)}")
        else:
            # Base64 编码
            try:
                # 支持 data:xxx;base64,xxx 格式
                if "," in file and "base64" in file.split(",")[0]:
                    _, encoded = file.split(",", 1)
                else:
                    encoded = file
                content = base64.b64decode(encoded)
            except Exception as e:
                return fail(f"Invalid base64 file format: {str(e)}")
        original_filename = save_path.name
    else:
        return fail("file parameter is required", status_code=400)


    # 检查是否为 zip 文件
    is_zip_file = (
            path.lower().endswith('.zip') or
            (len(content) > 4 and content[:4] == b'PK\x03\x04')
    )


    try:
        # 写入文件
        await write_file_async(save_path, content)

        # 构建响应
        resp = {
            "success": True,
            "file": {
                "name": save_path.name,
                "type": "file",
                "path": str(save_path),
                "size": len(content)
            }
        }

        # 如果是 zip 文件且需要自动解压
        if is_zip_file and auto_unzip:
            # 获取解压目标目录
            if path.lower().endswith('.zip'):
                extract_dir = save_path.parent / save_path.stem
            else:
                extract_dir = save_path.parent / f"{save_path.name}_extracted"

            # 在线程池中执行解压（避免阻塞）
            unzip_result = await run_in_threadpool(
                lambda: extract_zip_file(save_path, extract_dir)
            )

            resp["unzip"] = unzip_result


        return ok(resp)

    except PermissionError:
        return fail("Permission denied", status_code=403)
    except Exception as e:
        return fail(f"Failed to upload file: {str(e)}", status_code=500)


@router.post("/file/operation", description="文件操作接口")
async def operate_file(payload: FileCommonOperationRequest):
    if payload.operation in ["rename", "copy", "move"] and not payload.target_path:
        return fail("Target path parameter is required", status_code=400)

    if payload.operation != "mkdir" and not os.path.exists(payload.original_path):
        return fail("Origin path does not exist", status_code=404)

    try:
        src = Path(payload.original_path)
        if payload.operation == "mkdir":
            os.makedirs(payload.original_path, exist_ok=True)
        elif payload.operation == "copy":
            if src.is_dir():
                await run_in_threadpool(
                    lambda: shutil.copytree(payload.original_path, payload.target_path)
                )
            elif src.is_file():
                await run_in_threadpool(
                    lambda: shutil.copy(payload.original_path, payload.target_path)
                )
        elif payload.operation == "move":
            await run_in_threadpool(
                lambda: shutil.move(payload.original_path, payload.target_path)
            )
        elif payload.operation == "rename":
            if src.is_dir():
                return fail(f"{payload.original_path} is not a file")
            await run_in_threadpool(
                lambda: src.rename(payload.target_path)
            )
        elif payload.operation == "remove":
            if src.is_dir():
                await run_in_threadpool(
                    lambda: shutil.rmtree(payload.original_path)
                )
            elif src.is_file():
                await run_in_threadpool(
                    lambda: src.unlink()
                )
        resp = {
            "operation": payload.operation,
            "target_path": payload.target_path,
            "original_path": payload.original_path,
        }
        return ok(resp)

    except Exception as e:
        return fail(f"Failed to operate file: {str(e)}", status_code=500)


async def _handle_base64_download(file_path: Path, original_path: str, is_dir: bool):
    """处理 base64 格式下载"""

    def op():
        if is_dir:
            # 压缩目录
            zip_path = _create_zip_from_directory(file_path)
            try:
                content = _read_file_as_base64(zip_path)
                filename = f"{file_path.name}.zip"
            finally:
                # 清理临时文件
                zip_path.unlink(missing_ok=True)
        else:
            content = _read_file_as_base64(file_path)
            filename = file_path.name

        return content, filename

    try:
        content, filename = await run_in_threadpool(op)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")

    return ok({
        "format": "base64",
        "path": original_path,
        "content": content,
        "filename": filename,
    })


async def _handle_text_download(file_path: Path, original_path: str):
    """处理 text 格式下载"""

    def op():
        return _read_file_as_text(file_path)

    try:
        content = await run_in_threadpool(op)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")

    return ok({
        "format": "text",
        "path": original_path,
        "content": content,
        "filename": file_path.name,
    })


async def _handle_file_stream_download(file_path: Path, original_path: str, is_dir: bool):
    """处理文件流式下载"""

    temp_zip_path: Optional[Path] = None

    if is_dir:
        # 压缩目录
        def create_zip():
            return _create_zip_from_directory(file_path)

        try:
            temp_zip_path = await run_in_threadpool(create_zip)
        except PermissionError:
            raise HTTPException(status_code=403, detail="Permission denied")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to compress directory: {str(e)}")

        download_path = temp_zip_path
        filename = f"{file_path.name}.zip"
        media_type = "application/zip"
    else:
        download_path = file_path
        filename = file_path.name
        # 根据文件扩展名设置 media_type
        media_type = "application/octet-stream"

    async def file_iterator():
        """异步文件迭代器"""
        chunk_size = 64 * 1024  # 64KB chunks
        try:
            with open(download_path, "rb") as f:
                while chunk := f.read(chunk_size):
                    yield chunk
        finally:
            # 清理临时 zip 文件
            if temp_zip_path and temp_zip_path.exists():
                try:
                    temp_zip_path.unlink()
                except Exception:
                    pass

    return StreamingResponse(
        file_iterator(),
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}; filename=\"{filename.encode('utf-8').decode('latin-1', 'ignore')}\""
        }
    )


def _iso(dt: Optional[float]) -> Optional[str]:
    if dt is None:
        return None
    return datetime.fromtimestamp(dt, tz=timezone.utc).isoformat()


def _stat_to_entry(p: Path) -> dict[str, Any]:
    st = p.stat()
    is_dir = p.is_dir()

    return {
        "path": str(p),
        "name": p.name,
        "size": None if is_dir else int(st.st_size),
        "modified_time": _iso(st.st_mtime),
        "created_time": _iso(getattr(st, "st_birthtime", None) or st.st_ctime),
        "type": "dir" if is_dir else "file",
    }


def _list_entries(root: Path, depth: int) -> list[dict[str, Any]]:
    if not root.exists():
        raise FileNotFoundError(str(root))

    out: list[dict[str, Any]] = []

    def walk(p: Path, d: int):
        out.append(_stat_to_entry(p))
        if d <= 0 or not p.is_dir():
            return

        for child in p.iterdir():
            walk(child, d - 1)

    walk(root, depth)
    return out


def _should_exclude(path: Path) -> bool:
    """检查路径是否应该被排除"""
    # 检查目录名
    for part in path.parts:
        if part in EXCLUDE_PATTERNS:
            return True

    # 检查文件扩展名
    if path.suffix.lower() in EXCLUDE_EXTENSIONS:
        return True

    # 检查文件名（如 .DS_Store）
    if path.name in EXCLUDE_PATTERNS:
        return True

    return False


def _create_zip_from_directory(dir_path: Path) -> Path:
    return create_zip_from_directory(
        dir_path,
        exclude_patterns=EXCLUDE_PATTERNS,
        exclude_extensions=EXCLUDE_EXTENSIONS,
    )


def _read_file_as_base64(file_path: Path) -> str:
    return read_file_as_base64(file_path)


def _read_file_as_text(file_path: Path) -> str:
    return read_file_as_text(file_path)