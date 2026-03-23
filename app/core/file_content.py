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


import json


def extract_and_parse_json(dirty_string: str) -> dict:
    """
    从混杂日志的字符串中提取 JSON 并解析。
    - 以 { 开头：倒序找最后一个 }，丢掉后面
    - 以 } 结尾：正序找第一个 {，丢掉前面
    - 都不是：两头都裁
    """
    s = dirty_string.strip()

    if s.startswith("{"):
        # 倒序找最后一个 }
        end = s.rfind("}")
        if end == -1:
            raise ValueError("找不到匹配的 }")
        s = s[:end + 1]
    elif s.endswith("}"):
        # 正序找第一个 {
        start = s.find("{")
        if start == -1:
            raise ValueError("找不到匹配的 {")
        s = s[start:]
    else:
        # 两头都不是，两边都裁
        start = s.find("{")
        end = s.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("找不到 JSON 对象")
        s = s[start:end + 1]

    # 清洗中间的日志行
    lines = s.splitlines()
    clean_lines = [line for line in lines if not line.strip().startswith("[plugins]")]
    clean_string = "\n".join(clean_lines)

    return json.loads(clean_string)


# 测试
if __name__ == "__main__":
    # 场景1: { 开头，后面跟日志
    test1 = """{
    "name": "test",
    "status": "ok"
}
[plugins] feishu_doc: Registered feishu_doc
[plugins] feishu_chat: Registered feishu_chat tool"""

    # 场景2: 日志在前，} 结尾
    test2 = """[plugins] feishu_doc: Registered feishu_doc
[plugins] feishu_chat: Registered feishu_chat tool
{
    "name": "test",
    "status": "ok"
}"""

    # 场景3: 两头都有日志
    test3 = """[plugins] feishu_doc: Registered feishu_doc
{
    "name": "test",
    "status": "ok"
}
[plugins] feishu_chat: Registered feishu_chat tool"""

    # 场景4: 中间也有日志
    test4 = """[plugins] feishu_doc: Registered feishu_doc
{
    "name": "test",
[plugins] feishu_wiki: Registered feishu_wiki tool
    "data": {"key": "value"},
[plugins] feishu_drive: Registered feishu_drive tool
    "status": "ok"
}
[plugins] feishu_bitable: Registered bitable tools"""

    for i, test in enumerate([test1, test2, test3, test4], 1):
        print(f"场景{i}: {json.dumps(extract_and_parse_json(test), ensure_ascii=False)}")
