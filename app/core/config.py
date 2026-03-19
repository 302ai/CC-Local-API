from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    APP_NAME: str = os.getenv("APP_NAME", "cc_local_api")
    DB_SQLITE_PATH: str = os.getenv("DB_SQLITE_PATH", "/home/user/db/app.db")
    ROOT_SAVE_PATH: str = os.getenv("ROOT_SAVE_PATH", "/home/user")

    ANTHROPIC_BASE_URL: str = os.getenv("ANTHROPIC_BASE_URL", "https://api.302.ai")
    ANTHROPIC_DEFAULT_HAIKU_MODEL: str = os.getenv("ANTHROPIC_DEFAULT_HAIKU_MODEL", "gpt-5.2")
    ANTHROPIC_DEFAULT_OPUS_MODEL: str = os.getenv("ANTHROPIC_DEFAULT_OPUS_MODEL", "gpt-5.2")
    ANTHROPIC_DEFAULT_SONNET_MODEL: str = os.getenv("ANTHROPIC_DEFAULT_SONNET_MODEL", "gpt-5.2")
    CLAUDE_CODE_SUBAGENT_MODEL: str = os.getenv("CLAUDE_CODE_SUBAGENT_MODEL", "gpt-5.2")
    ANTHROPIC_AUTH_TOKEN: str = os.getenv("ANTHROPIC_AUTH_TOKEN")




settings = Settings()

# 最大文件大小限制
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB

# 保存数据的根目录
ROOT_SAVE_PATH = settings.ROOT_SAVE_PATH

# Skills directories
CLAUDE_SKILLS_DIR = Path(ROOT_SAVE_PATH) / ".claude/skills"
OPENCLAW_SKILLS_DIR = Path(ROOT_SAVE_PATH) / ".openclaw/skills"
