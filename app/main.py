from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import asyncio
import datetime
import shutil

import aiohttp
from fastapi import FastAPI

from app.api.routes import cc_router, sandbox_router, chat_base_router
from app.core.common import short_hash
from app.core.config import ROOT_SAVE_PATH
from app.core.config import settings
from app.core.git_ops import validate_and_normalize_github_url
from app.core.log import log_info
from app.db.database import db_state_default
from app.models.base import bind_models, auto_migrate_add_missing_columns, detect_missing_columns
from app.models.skill import Skill
from app.models.session import Session


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = db_state_default()

    bind_models(app.state.db.database, [Skill, Session])

    models = [Skill, Session]

    # Detect whether migration is needed. If needed, backup first, then migrate.
    missing_cols = detect_missing_columns(app.state.db.database, models)
    if missing_cols:
        db_path = Path(settings.DB_SQLITE_PATH)
        if db_path.exists():
            ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup_path = db_path.with_suffix(db_path.suffix + f".bak.{ts}")
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(db_path, backup_path)
            log_info(
                "SQLite DB backup created before auto-migration.",
                db_path=str(db_path),
                backup_path=str(backup_path),
                missing_columns=len(missing_cols),
            )

        auto_migrate_add_missing_columns(app.state.db.database, models)

    async def _load_official_skills_once():
        github_url = "https://github.com/anthropics/skills.git"

        try:
            repo_url, _, _ = validate_and_normalize_github_url(github_url)
        except Exception as e:
            log_info(
                "Official skills url normalization failed; continue startup.",
                github_url=github_url,
                error=str(e),
            )
            return

        # If the repo hash directory already exists, skip initialization.
        repo_url_hash = short_hash(repo_url)
        repo_dir = Path(ROOT_SAVE_PATH) / ".claude/skills" / repo_url_hash
        if repo_dir.exists():
            log_info(
                "Official skills already initialized; skip.",
                github_url=github_url,
                repo_url=repo_url,
                repo_url_hash=repo_url_hash,
                repo_dir=str(repo_dir),
                root_save_path=str(ROOT_SAVE_PATH),
            )
            return

        log_info(
            "Scheduling official skills initialization.",
            github_url=github_url,
            repo_url=repo_url,
            repo_url_hash=repo_url_hash,
            repo_dir=str(repo_dir),
            root_save_path=str(ROOT_SAVE_PATH),
        )

        # Wait a few seconds for the server to be ready to accept requests.
        await asyncio.sleep(3)
        url = "http://127.0.0.1:8000/302/claude-code/skills"
        payload = {"github_url": github_url}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    await resp.read()
                    log_info(
                        "Official skills initialization request sent.",
                        github_url=github_url,
                        repo_url=repo_url,
                        status=resp.status,
                    )
        except Exception as e:
            # Best-effort: startup should not fail if skill loading fails.
            log_info(
                "Official skills initialization failed; continue startup.",
                github_url=github_url,
                repo_url=repo_url,
                error=str(e),
            )

    asyncio.create_task(_load_official_skills_once())
    yield


from app.core.request_id_middleware import RequestIDMiddleware


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)
app.add_middleware(RequestIDMiddleware)
app.include_router(cc_router)
app.include_router(sandbox_router)
app.include_router(chat_base_router)
