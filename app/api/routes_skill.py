from __future__ import annotations

import base64
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
from app.core.config import MAX_FILE_SIZE, ROOT_SAVE_PATH
from app.core.file_content import extract_zip_file, read_file_as_text_async, create_zip_from_directory
from app.core.file_io import download_file_from_url, write_file_async, sync_copy_dir_contents
from app.core.git_ops import validate_and_normalize_github_url, clone_github_repo
from app.core.log import log_error
from app.core.skill_ops import load_skills_from_dir, translate_skill_desc_to_zh
from app.db.session import get_db, run_in_threadpool
from app.repositories.skill_repo import SkillRepository


from pydantic import BaseModel, Field

router = APIRouter()



class SkillDeleteRequest(BaseModel):
    skill_list: list = Field([], description="skill_name list")
    skill_id_list: list = Field([], description="skill_id list")


def get_skill_repo(db=Depends(get_db)) -> SkillRepository:
    return SkillRepository(db)


@router.post("/skills")
async def create_skill(request: Request, repo: SkillRepository = Depends(get_skill_repo)):
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
        repo_url_hash = await run_in_threadpool(
            lambda: short_hash(repo_url)
        )
        final_skill_save_path = Path(ROOT_SAVE_PATH) / ".claude/skills" / repo_url_hash / name
        skill_zip_path = final_skill_save_path.with_suffix(".zip")
        await run_in_threadpool(
            lambda: sync_copy_dir_contents(skill_path, final_skill_save_path, clear_dst=True)
        )
        await run_in_threadpool(
            lambda: create_zip_from_directory(final_skill_save_path, zip_path=skill_zip_path)
        )
        try:
            description_zh = await translate_skill_desc_to_zh(description)
        except Exception as e:
            log_error(f"Translate skill [{name}] description fails, downgraded to save as an empty string")
            description_zh = ""

        def op():
            with repo.atomic():
                return repo.upsert_skill(
                    name=name,
                    skill_type="",
                    description_en=description,
                    description_zh=description_zh,
                    source_url=source_url,
                    source_url_hash=repo_url_hash,
                    local_path=final_skill_save_path,
                )

        await run_in_threadpool(op)
        skill_list.append({
            "name": name,
            "description": description,
            "description_zh": description_zh,
        })

    return ok({"user_skills": skill_list})

@router.get("/skills/detail")
async def skill_detail(request: Request,
                       name: str = Query("", description="skill名字"),
                       id: int = Query(None, description="skill id"),
                       mode: str = Query(..., description="返回数据格式 view返回md内容 edit返回zip文件"),
                       builtin: Optional[bool] = Query(False, description="是否是内置skill"),
                       repo: SkillRepository = Depends(get_skill_repo)):
    if mode not in ["view", "edit"]:
        return fail("mode is invalid", status_code=400)
    if not id and not name:
        return fail("id or name parameter is required", status_code=400)

    def op():
        with repo.atomic():
            if id:
                skill = repo.get_skill(id)
            else:
                skill = repo.get_skill_by_name(name)
            return skill

    skill_data = await run_in_threadpool(op)
    if not skill_data:
        return fail(f"skill [{name}] does not exist", status_code=404)
    if mode == "view":

        skill_path = Path(skill_data.local_path) / "SKILL.md"
        if skill_path.exists():
            skill_content = await read_file_as_text_async(skill_path)
        else:
            skill_content = ""
        return ok({"data": {"name": skill_data.name, "description": skill_data.description_en, "skill": skill_content}})
    else:
        final_skill_save_path = Path(ROOT_SAVE_PATH) / ".claude/skills" / skill_data.source_url_hash / skill_data.name
        skill_zip_path = final_skill_save_path.with_suffix(".zip")

        filename = f"{skill_data.name}.zip"

        def iterfile(file_path):
            with open(file_path, mode="rb") as file_like:
                yield from file_like

        return StreamingResponse(
            iterfile(skill_zip_path),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}; filename=\"{filename.encode('utf-8').decode('latin-1', 'ignore')}\""
            }
        )


@router.get("/skills/list")
async def skill_list(
    request: Request,
    limit: int = Query(50, description="每页数量"),
    offset: int = Query(0, description="偏移量"),
    repo: SkillRepository = Depends(get_skill_repo),
):
    def op():
        return repo.list_skills(limit=limit, offset=offset)

    result = await run_in_threadpool(op)  # SkillListResult(items, total)

    items = result.items
    total = result.total

    total_pages = math.ceil(total / limit) if limit > 0 else 0

    return ok({
        "user_skills": [
            {
                "id": skill.id,
                "name": skill.name,
                "description": skill.description_en,
                "description_zh": skill.description_zh,
            }
            for skill in items
        ],
        "builtin_skills": [],
        "project_skills": [],
        "pagination": {
            "total": total,
            "limit": limit,
            "offset": offset,
            "total_pages": total_pages,
        }
    })


@router.delete("/skills")
async def skill_delete(payload: SkillDeleteRequest, repo: SkillRepository = Depends(get_skill_repo),):
    delete_result = []
    for skill_name in payload.skill_list:
        skill_path = None
        skill_zip_path = None
        skill_id = ""

        def op(sname=skill_name):
            nonlocal skill_path, skill_zip_path, skill_id
            skill_data = repo.get_skill_by_name(sname)
            if not skill_data:
                return {
                    "success": False,
                    "message": f"skill_name [{sname}] does not exist",
                    "name": sname,
                    "id": "",
                }

            # 保存路径信息供事务外使用
            skill_path = Path(skill_data.local_path)
            skill_zip_path = skill_path.with_suffix(".zip")
            skill_id = skill_data.id  # 根据实际字段调整

            # 只删数据库
            repo.delete_skill(skill_id)
            return None  # 表示数据库删除成功

        with repo.atomic():
            result = await run_in_threadpool(op)

        # 如果数据库删除失败，直接记录结果
        if result is not None:
            delete_result.append(result)
            continue

        # 事务外删除文件，不存在则跳过
        shutil.rmtree(skill_path, ignore_errors=True)
        if skill_zip_path.exists():
            try:
                os.remove(skill_zip_path)
            except OSError:
                pass

        delete_result.append({
            "success": True,
            "message": "delete success",
            "name": skill_name,
            "id": skill_id,
        })

    return ok({"data": {"result": delete_result}})

