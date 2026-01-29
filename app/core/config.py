from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    APP_NAME: str = os.getenv("APP_NAME", "fastapi-peewee-skeleton")
    DB_SQLITE_PATH: str = os.getenv("DB_SQLITE_PATH", "app.db")
    ROOT_SAVE_PATH: str = os.getenv("ROOT_SAVE_PATH", r"C:\Users\hjj\Desktop\222")

    ANTHROPIC_BASE_URL: str = os.getenv("ANTHROPIC_BASE_URL", "https://api.302.ai")
    ANTHROPIC_DEFAULT_HAIKU_MODEL: str = os.getenv("ANTHROPIC_DEFAULT_HAIKU_MODEL", "gpt-5.2")
    ANTHROPIC_AUTH_TOKEN: str = os.getenv("ANTHROPIC_AUTH_TOKEN")




settings = Settings()

# 最大文件大小限制
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB

# 保存数据的根目录
ROOT_SAVE_PATH = settings.ROOT_SAVE_PATH