from __future__ import annotations

import shutil
from pathlib import Path

import aiofiles
import aiohttp


async def download_file_from_url(url: str) -> bytes:
    """从 URL 下载文件内容"""
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as response:
            if response.status != 200:
                raise Exception(f"Failed to download file: HTTP {response.status}")
            return await response.read()


async def write_file_async(file_path: Path, content: bytes | str):
    """异步写入文件"""
    file_path.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(content, str):
        # 文本模式
        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(content)
    else:
        # 二进制模式
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)


def write_file_sync(file_path: Path, content: bytes):
    """同步写入文件（用于线程池）"""
    file_path.parent.mkdir(parents=True, exist_ok=True)

    with open(file_path, "wb") as f:
        f.write(content)


def sync_copy_dir_contents(src_dir, dst_dir, *, clear_dst=False):
    """
    Copy the content under src_dir to dst_dir (excluding the src_dir layer).
    When clear_dst=True: Delete dst_dir before rebuilding to ensure that the old data is not mixed.
    """
    src = Path(src_dir)
    dst = Path(dst_dir)

    if not src.is_dir():
        raise NotADirectoryError(f"src_dir is not a directory: {src}")

    if clear_dst:
        shutil.rmtree(dst, ignore_errors=True)
        dst.mkdir(parents=True, exist_ok=True)
    else:
        dst.mkdir(parents=True, exist_ok=True)

    for p in src.iterdir():
        target = dst / p.name
        if p.is_dir():
            # 若 clear_dst=False 且 target 已存在会报错；需要覆盖可改成 dirs_exist_ok=True
            shutil.copytree(p, target)
        else:
            shutil.copy2(p, target)