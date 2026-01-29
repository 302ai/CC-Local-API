from __future__ import annotations

import base64
import os
import tempfile
import zipfile
from pathlib import Path
import aiofiles


def should_exclude(path: Path, *, exclude_patterns: set[str], exclude_extensions: set[str]) -> bool:
    """检查路径是否应该被排除"""
    for part in path.parts:
        if part in exclude_patterns:
            return True

    if path.suffix.lower() in exclude_extensions:
        return True

    if path.name in exclude_patterns:
        return True

    return False




def create_zip_from_directory(
    dir_path: Path,
    *,
    exclude_patterns: set[str] | None = None,
    exclude_extensions: set[str] | None = None,
    zip_path: Path | None = None,
) -> Path:
    """将目录压缩为 zip 文件。
    - zip_path 提供则写入该路径（覆盖同名文件）
    - 否则写入临时 zip 文件
    exclude_patterns / exclude_extensions 不传则默认为空集合
    """
    exclude_patterns = exclude_patterns or set()
    exclude_extensions = exclude_extensions or set()

    dir_path = Path(dir_path)

    if zip_path is None:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        zip_path = Path(tmp.name)
        tmp.close()
    else:
        zip_path = Path(zip_path)
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        if zip_path.exists():
            zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(dir_path):
            root_path = Path(root)

            dirs[:] = [
                d
                for d in dirs
                if not should_exclude(
                    root_path / d,
                    exclude_patterns=exclude_patterns,
                    exclude_extensions=exclude_extensions,
                )
            ]

            for file in files:
                file_path = root_path / file

                if should_exclude(
                    file_path,
                    exclude_patterns=exclude_patterns,
                    exclude_extensions=exclude_extensions,
                ):
                    continue

                arcname = file_path.relative_to(dir_path)
                zipf.write(file_path, arcname)

    return zip_path



def extract_zip_file(zip_path: Path, extract_dir: Path) -> dict:
    """解压 ZIP 文件"""
    try:
        # 创建解压目录
        extract_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # 检查是否有非法路径（路径遍历攻击防护）
            for member in zip_ref.namelist():
                member_path = extract_dir / member
                if not str(member_path.resolve()).startswith(str(extract_dir.resolve())):
                    raise ValueError(f"Illegal path in zip: {member}")

            zip_ref.extractall(extract_dir)

        # 删除原 zip 文件
        zip_path.unlink()

        return {
            "success": True,
            "extracted_to": str(extract_dir),
            "message": "File unzipped successfully"
        }
    except zipfile.BadZipFile as e:
        return {
            "success": False,
            "error": f"Invalid zip file: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def read_file_as_base64(file_path: Path) -> str:
    """读取文件并返回 base64 编码"""
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def read_file_as_text(file_path: Path) -> str:
    """读取文件并返回文本内容"""
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


async def read_file_as_text_async(file_path: Path) -> str:
    """异步读取文件并返回文本内容"""
    async with aiofiles.open(file_path, "r", encoding="utf-8", errors="replace") as f:
        return await f.read()