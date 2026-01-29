import os
import re
from typing import Any, Dict, List, Optional

import asyncio
import yaml

from app.core.config import settings
from app.core.http_client import fetch_json_with_retry
from app.prompt.skill_desc_translate import SKILL_DESC_TRANSLATION_TO_ZH_SYSTEM_PROMPT


def _extract_front_matter(md_text: str) -> Optional[str]:
    if md_text.startswith("\ufeff"):
        md_text = md_text.lstrip("\ufeff")

    lines = md_text.splitlines()
    i = 0
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    if i >= len(lines) or lines[i].strip() != "---":
        return None

    j = i + 1
    while j < len(lines):
        if lines[j].strip() == "---":
            return "\n".join(lines[i + 1 : j])
        j += 1
    return None

def parse_skill_file(fp: str, debug: bool = False) -> Optional[Dict[str, Any]]:
    """
    解析单个 SKILL.md，成功返回:
      {"name": str, "description": str, "path": str}
    失败返回 None（包括读不到、无 front matter、yaml 非法等情况）。
    """
    try:
        with open(fp, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception as e:
        if debug:
            print(f"[debug] unreadable: {fp} ({e})")
        return None

    fm = _extract_front_matter(text)
    if not fm:
        if debug:
            print(f"[debug] no_front_matter: {fp}")
        return None

    try:
        meta = yaml.safe_load(fm) or {}
    except Exception as e:
        if debug:
            print(f"[debug] bad_yaml: {fp} ({e})")
        meta = {}

    if not isinstance(meta, dict):
        if debug:
            print(f"[debug] meta_not_dict: {fp} (type={type(meta).__name__})")
        meta = {}
    name = str(meta.get("name") or "").strip() or os.path.basename(os.path.dirname(fp))
    desc = str(meta.get("description") or "").strip()

    return {"name": name, "description": desc, "path": os.path.dirname(fp), "md_content": fm}

def load_skills_from_dir(dir_path: str, debug: bool = False) -> List[Dict[str, Any]]:
    dir_path = os.path.abspath(os.path.expanduser(dir_path))
    if not os.path.isdir(dir_path):
        raise ValueError(f"不是目录或不存在：{dir_path}")

    skill_files: List[str] = []
    for root, _, files in os.walk(dir_path):
        for fn in files:
            if fn == "SKILL.md":
                skill_files.append(os.path.join(root, fn))

    if debug:
        print(f"[debug] scan_dir={dir_path}")
        print(f"[debug] found_SKILL_md={len(skill_files)}")

    results: List[Dict[str, Any]] = []
    for fp in sorted(skill_files):
        try:
            with open(fp, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            if debug:
                print(f"[debug] unreadable: {fp} ({e})")
            continue

        fm = _extract_front_matter(text)
        if not fm:
            if debug:
                print(f"[debug] no_front_matter: {fp}")
            continue

        try:
            meta = yaml.safe_load(fm) or {}
        except Exception as e:
            if debug:
                print(f"[debug] bad_yaml: {fp} ({e})")
            meta = {}

        if not isinstance(meta, dict):
            if debug:
                print(f"[debug] meta_not_dict: {fp} (type={type(meta).__name__})")
            meta = {}

        name = str(meta.get("name") or "").strip() or os.path.basename(os.path.dirname(fp))
        desc = str(meta.get("description") or "").strip()

        results.append({"name": name, "description": desc, "path": os.path.dirname(fp)})

    if debug:
        print(f"[debug] parsed_skills={len(results)}")
    return results

async def translate_skill_desc_to_zh(skill_desc: str, llm_model: str="gemini-2.5-flash-lite") -> str:

    headers = {
        "Authorization": f"Bearer {settings.ANTHROPIC_AUTH_TOKEN}",
    }
    messages = [
        {
            "role": "system",
            "content": SKILL_DESC_TRANSLATION_TO_ZH_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": skill_desc,
        }
    ]
    payload = {
        "model": llm_model,
        "messages": messages,
        # "max_tokens": 4096,
        # "stream": True
    }

    data = await fetch_json_with_retry(
        "POST",
        f"{settings.ANTHROPIC_BASE_URL}/chat/completions",
        headers=headers,
        json=payload,
        session=None,
        retries=3,
        timeout=30,
    )

    translation_result_str = data["choices"][0]["message"]["content"]
    # fix md格式返回
    regex = re.compile(r"```(?:json)?(.*?)```", re.DOTALL)
    match = regex.search(translation_result_str)
    if match:
        translation_result_str = match.group(1)

    return translation_result_str
