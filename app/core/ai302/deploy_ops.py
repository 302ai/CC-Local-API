import json
from pathlib import Path

import aiohttp

from app.core.config import settings
from app.core.http_client import fetch_json_with_retry


async def create_302ai_deploy_task(
        zip_path: Path,
        session: aiohttp.ClientSession | None = None,
        headers: dict | None = None,
        env: dict | None = None,
        update_subdomain: str | None = None,
):
    """上传 zip 文件，确保文件正确关闭"""

    # 使用 with 确保文件关闭
    with open(zip_path, 'rb') as f:
        form_data = aiohttp.FormData()
        form_data.add_field(
            name='project_file',
            value=f,
            filename=zip_path.name,
            content_type='application/zip'
        )

        if env:
            form_data.add_field(
                name='env',
                value=json.dumps(env),
                content_type='application/json'
            )

        if update_subdomain:
            form_data.add_field("update_subdomain", value=update_subdomain)

        response = await fetch_json_with_retry(
            'POST',
            f"https://api.302.ai/302/webserve/project",
            session=session,
            data=form_data,
            headers=headers
        )

    return response


async def get_302ai_deploy_task_info(deploy_project_id, headers: dict | None = None):
    return await fetch_json_with_retry("GET",
                                f"https://api.302.ai/302/webserve/project?project_id={deploy_project_id}",
                                headers=headers)