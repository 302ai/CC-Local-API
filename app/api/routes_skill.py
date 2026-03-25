from __future__ import annotations

import base64
import hashlib
import io
import math
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

import aiofiles
from fastapi import APIRouter, Depends, Request, Query
from starlette.datastructures import UploadFile
from starlette.responses import StreamingResponse

from app.api.request import parse_request_data
from app.api.response import fail, ok
from app.core.common import short_hash
from app.core.command_runner import CommandRunner
from app.core.config import MAX_FILE_SIZE, CLAUDE_SKILLS_DIR, OPENCLAW_SKILLS_DIR
from app.core.file_content import extract_zip_file, read_file_as_text_async, create_zip_from_directory, \
    extract_and_parse_json
from app.core.file_io import download_file_from_url, write_file_async, sync_copy_dir_contents
from app.core.git_ops import validate_and_normalize_github_url, clone_github_repo
from app.core.log import log_error
from app.core.skill_ops import load_skills_from_dir, translate_skill_desc_to_zh
from app.db.session import get_db, run_in_threadpool
from app.repositories.skill_desc_zh_cache_repo import SkillDescZhCacheRepository


from pydantic import BaseModel, Field

router = APIRouter()



class SkillDeleteRequest(BaseModel):
    skill_list: list = Field([], description="skill_name list")
    skill_id_list: list = Field([], description="skill_id list")


def get_skill_desc_cache_repo(db=Depends(get_db)) -> SkillDescZhCacheRepository:
    return SkillDescZhCacheRepository(db)


@router.post("/skills")
async def create_skill(request: Request, repo: SkillDescZhCacheRepository = Depends(get_skill_desc_cache_repo)):
    """

    用户上传zip压缩包或者提供github链接，将数据先下载到临时文件，遍历寻找SKILL.md拷贝到实际保存位置

    skill名字/描述通过解析SKILL.md里的yaml元信息获得

    :param request:
    :param repo:
    :return:
    """
    # 检查请求体大小
    content_length = request.headers.get('content-length')
    if content_length and int(content_length) > MAX_FILE_SIZE:
        return fail(f"Request body too large. Maximum size is 20MB, got {int(content_length) / 1024 / 1024:.2f}MB",
                    status_code=413)

    # 解析请求数据
    body = await parse_request_data(request)

    # 参数验证
    file = body.get("file", "")
    github_url = body.get("github_url", "")
    branch = body.get("branch")
    if not file and not github_url:
        return fail("No file or github_url specified", status_code=400)
    base_temp_dir = tempfile.mkdtemp(prefix="temp_skill_")
    extract_dir = Path(base_temp_dir) / "extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)
    if file:
        source_url = "unknown"
        repo_url = "unknown"
        # 处理文件内容
        if isinstance(file, UploadFile):
            # multipart/form-data 上传的文件
            content = await file.read()
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
        else:
            return fail("file parameter is required", status_code=400)

        # ZIP 校验
        if not zipfile.is_zipfile(io.BytesIO(content)):
            return fail("zip file parameter is required", status_code=400)
        zip_save_path = Path(base_temp_dir) / "user_skills.zip"

        await write_file_async(zip_save_path, content)

        # 在线程池中执行解压（避免阻塞）
        unzip_result = await run_in_threadpool(
            lambda: extract_zip_file(zip_save_path, extract_dir)
        )
    else:

        repo_url, subpath, url_branch = await run_in_threadpool(
            lambda: validate_and_normalize_github_url(github_url)
        )
        # The database only stores the main address of the GitHub repository and does not store more specific paths,
        # which is convenient for making unique judgments based on GitHub repository name + skill name
        source_url = repo_url
        final_branch = url_branch or branch
        await run_in_threadpool(
            lambda: clone_github_repo(repo_url, str(extract_dir), branch=final_branch, sparse_path=subpath)
        )

    find_all_skills = await run_in_threadpool(
            lambda: load_skills_from_dir(str(extract_dir))
        )
    skill_list = []
    for skill_info in find_all_skills:
        name = skill_info["name"]
        description = skill_info["description"]
        skill_path = skill_info["path"]

        final_skill_save_path = CLAUDE_SKILLS_DIR / name
        skill_zip_path = final_skill_save_path.with_suffix(".zip")

        await run_in_threadpool(
            lambda: sync_copy_dir_contents(skill_path, final_skill_save_path, clear_dst=True)
        )
        await run_in_threadpool(
            lambda: create_zip_from_directory(final_skill_save_path, zip_path=skill_zip_path)
        )

        desc_key = await run_in_threadpool(
            lambda: short_hash(description)
        )

        def cache_get_op(key=desc_key):
            with repo.atomic():
                row = repo.get_by_md5_16(key)
                return row.description_zh if row else None

        description_zh = await run_in_threadpool(cache_get_op)

        if not description_zh:
            try:
                description_zh = await translate_skill_desc_to_zh(description)
            except Exception:
                log_error(f"Translate skill [{name}] description fails, downgraded to save as an empty string")
                description_zh = ""

            def cache_put_op(key=desc_key, desc=description, zh=description_zh):
                with repo.atomic():
                    return repo.upsert(description_md5_16=key, description=desc, description_zh=zh)
            if description_zh:
                await run_in_threadpool(cache_put_op)

        skill_list.append({
            "name": name,
            "description": description,
            "description_zh": description_zh,
        })

    return ok({"user_skills": skill_list})

@router.get("/skills/detail")
async def skill_detail(
    _request: Request,
    name: str = Query("", description="skill名字"),
    mode: str = Query(..., description="返回数据格式 view返回md内容 edit返回zip文件"),
):
    if mode not in ["view", "edit"]:
        return fail("mode is invalid", status_code=400)
    if not name:
        return fail("name parameter is required", status_code=400)

    def iterfile(file_path: Path):
        with open(file_path, mode="rb") as file_like:
            yield from file_like

    for root in (CLAUDE_SKILLS_DIR, OPENCLAW_SKILLS_DIR):
        skill_dir = root / name
        skill_md = skill_dir / "SKILL.md"
        skill_zip = root / f"{name}.zip"

        if mode == "view":
            if not skill_md.exists():
                continue
            skill_content = await read_file_as_text_async(skill_md)
            return ok({"data": {"name": name, "description": "", "skill": skill_content}})

        # mode == "edit"
        if skill_zip.exists():
            filename = f"{name}.zip"
            return StreamingResponse(
                iterfile(skill_zip),
                media_type="application/octet-stream",
                headers={
                    "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}; filename=\"{filename.encode('utf-8').decode('latin-1', 'ignore')}\""
                },
            )

        if skill_dir.exists():
            await run_in_threadpool(lambda: create_zip_from_directory(skill_dir, zip_path=skill_zip))
            filename = f"{name}.zip"
            return StreamingResponse(
                iterfile(skill_zip),
                media_type="application/octet-stream",
                headers={
                    "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}; filename=\"{filename.encode('utf-8').decode('latin-1', 'ignore')}\""
                },
            )

    return fail(f"skill [{name}] does not exist", status_code=404)


@router.get("/skills/list")
async def skill_list(
    _request: Request,
    limit: int = Query(50, description="每页数量"),
    offset: int = Query(0, description="偏移量"),
    cache_repo: SkillDescZhCacheRepository = Depends(get_skill_desc_cache_repo),
):
    # 直接通过 openclaw CLI 获取 skill 列表（包含 source 等信息）
    oc_runner = CommandRunner()
    oc_result = await oc_runner.exec_json("openclaw skills list --json")

    oc_skills: list[dict] = []
    if oc_result.exit_code == 0:
        try:
            import json

            loaded = json.loads(oc_result.stdout or oc_result.stderr)  # 升级到openclaw 2026.3.22-2版本后，获取skills的结果意外输出到stderr
            # openclaw skills list --json 输出为 { ..., "skills": [...] }
            if isinstance(loaded, dict) and isinstance(loaded.get("skills"), list):
                oc_skills = [x for x in loaded["skills"] if isinstance(x, dict)]
            # 兼容旧格式：直接返回 list
            elif isinstance(loaded, list):
                oc_skills = [x for x in loaded if isinstance(x, dict)]
        except Exception:
            loaded = extract_and_parse_json(oc_result.stdout)
            # openclaw skills list --json 输出为 { ..., "skills": [...] }
            if isinstance(loaded, dict) and isinstance(loaded.get("skills"), list):
                oc_skills = [x for x in loaded["skills"] if isinstance(x, dict)]
            # 兼容旧格式：直接返回 list
            elif isinstance(loaded, list):
                oc_skills = [x for x in loaded if isinstance(x, dict)]

    total = len(oc_skills)
    total_pages = math.ceil(total / limit) if limit > 0 else 0

    items = oc_skills
    if limit > 0:
        items = oc_skills[offset : offset + limit]

    # 复用 create_skill 的翻译缓存逻辑：按 description 的 md5_16 缓存中文
    zh_by_md5: dict[str, str] = {}

    def _md5_16(s: str) -> str:
        return hashlib.md5(s.encode("utf-8")).hexdigest()[:16]

    desc_pairs: list[tuple[str, str]] = []  # (md5_16, description)
    for s in items:
        if not isinstance(s, dict):
            continue
        desc = s.get("description")
        if not isinstance(desc, str) or not desc:
            continue
        key = _md5_16(desc)
        desc_pairs.append((key, desc))

    # 先批量查缓存（逐条 get）
    for key, desc in desc_pairs:
        def _get_once(k=key):
            with cache_repo.atomic():
                row = cache_repo.get_by_md5_16(k)
                return row.description_zh if row else None

        cached = await run_in_threadpool(_get_once)
        if isinstance(cached, str) and cached:
            zh_by_md5[key] = cached

    # 缓存未命中的再翻译并写入
    for key, desc in desc_pairs:
        if key in zh_by_md5:
            continue
        try:
            zh = await translate_skill_desc_to_zh(desc)
        except Exception:
            zh = ""
        if zh:
            def _put_once(k=key, d=desc, z=zh):
                with cache_repo.atomic():
                    return cache_repo.upsert(description_md5_16=k, description=d, description_zh=z)

            await run_in_threadpool(_put_once)
            zh_by_md5[key] = zh

    return ok(
        {
            "user_skills": [
                {
                    "id": "",
                    "name": (s.get("name") or "") if isinstance(s.get("name"), str) else "",
                    "description": (s.get("description") or "") if isinstance(s.get("description"), str) else "",
                    "description_zh": zh_by_md5.get(_md5_16(s.get("description")))
                    if isinstance(s.get("description"), str) and s.get("description")
                    else "",
                    "source":"openclaw-bundled" if (isinstance(s.get("name"), str) and s.get("name") == "302ai-search") else ((s.get("source") or "") if isinstance(s.get("source"), str) else ""),
                    "eligible": bool(s.get("eligible")) if "eligible" in s else None,
                    "disabled": bool(s.get("disabled")) if "disabled" in s else None,
                    "bundled": bool(s.get("bundled")) if "bundled" in s else None,
                    "blockedByAllowlist": bool(s.get("blockedByAllowlist")) if "blockedByAllowlist" in s else None,
                    "missing": s.get("missing") if isinstance(s.get("missing"), dict) else None,
                }
                for s in items
                if isinstance(s, dict)
            ],
            "builtin_skills": [],
            "project_skills": [],
            "pagination": {
                "total": total,
                "limit": limit,
                "offset": offset,
                "total_pages": total_pages,
            },
        }
    )


@router.delete("/skills")
async def skill_delete(
    payload: SkillDeleteRequest,
):
    delete_result = []

    for name in payload.skill_list:
        if not name:
            delete_result.append({
                "success": False,
                "message": "skill_name is required",
                "name": name,
            })
            continue

        deleted_any = False

        for root in (CLAUDE_SKILLS_DIR, OPENCLAW_SKILLS_DIR):
            skill_dir = root / name
            skill_zip = root / f"{name}.zip"

            if skill_dir.exists():
                shutil.rmtree(skill_dir, ignore_errors=True)
                deleted_any = True

            if skill_zip.exists():
                try:
                    os.remove(skill_zip)
                    deleted_any = True
                except OSError:
                    pass

            if deleted_any:
                break

        if not deleted_any:
            delete_result.append({
                "success": False,
                "message": f"skill_name [{name}] does not exist",
                "name": name,
            })
            continue

        delete_result.append({
            "success": True,
            "message": "delete success",
            "name": name,
        })

    return ok({"data": {"result": delete_result}})

