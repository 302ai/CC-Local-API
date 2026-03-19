from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import asyncio
import datetime
import shutil

import aiohttp
from fastapi import FastAPI

from app.api.routes import cc_router, sandbox_router, chat_base_router, oc_base_router
from app.core.config import ROOT_SAVE_PATH
from app.core.config import settings
from app.core.git_ops import validate_and_normalize_github_url
from app.core.log import log_info
from app.db.database import db_state_default
from app.models.base import bind_models, auto_migrate_add_missing_columns, detect_missing_columns
from app.models.skill import Skill
from app.models.session import Session
from app.models.job_session_agent import JobSessionAgent
from app.models.skill_desc_zh_cache import SkillDescZhCache



@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = db_state_default()

    bind_models(app.state.db.database, [Skill, Session, JobSessionAgent, SkillDescZhCache])

    models = [Skill, Session, JobSessionAgent, SkillDescZhCache]

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
        version_path = Path("/home/user/.skill_sync_version.json")

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        should_sync = True

        try:
            raw = version_path.read_text(encoding="utf-8")
            import json
            payload = json.loads(raw)
            last = payload.get("last_sync_date") if isinstance(payload, dict) else None
            if isinstance(last, str) and last:
                try:
                    last_dt = datetime.datetime.fromisoformat(last.replace("Z", "+00:00"))
                    if (now_utc - last_dt).days < 15:
                        should_sync = False
                except Exception:
                    should_sync = True
        except FileNotFoundError:
            should_sync = True
        except Exception:
            should_sync = True

        if not should_sync:
            log_info("Official skills sync skipped (within 15 days).", version_path=str(version_path))
            return

        try:
            repo_url, _, _ = validate_and_normalize_github_url(github_url)
        except Exception as e:
            log_info(
                "Official skills url normalization failed; continue startup.",
                github_url=github_url,
                error=str(e),
            )
            return

        log_info(
            "Scheduling official skills initialization.",
            github_url=github_url,
            repo_url=repo_url,
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

                    if resp.status < 400:
                        import json
                        version_path.write_text(
                            json.dumps(
                                {"last_sync_date": now_utc.isoformat().replace("+00:00", "Z")},
                                ensure_ascii=False,
                            ),
                            encoding="utf-8",
                        )
        except Exception as e:
            # Best-effort: startup should not fail if skill loading fails.
            log_info(
                "Official skills initialization failed; continue startup.",
                github_url=github_url,
                repo_url=repo_url,
                error=str(e),
            )

    async def _sync_oc_cron_jobs_forever():
        from app.db.database import connect_db, close_db
        from app.db.session import run_in_threadpool
        from app.repositories.job_session_agent_repo import JobSessionAgentRepository

        jobs_path = Path("/home/user/.openclaw/cron/jobs.json")

        while True:
            try:
                raw = jobs_path.read_text(encoding="utf-8")
                import json
                payload = json.loads(raw)
                jobs = payload.get("jobs") if isinstance(payload, dict) else None
                if not isinstance(jobs, list):
                    raise ValueError("jobs.json missing 'jobs' list")
            except FileNotFoundError:
                await asyncio.sleep(60)
                continue
            except Exception as e:
                log_info("OpenClaw jobs sync skipped.", error=str(e))
                await asyncio.sleep(60)
                continue

            normalized: list[dict] = []
            for job in jobs:
                if not isinstance(job, dict):
                    continue
                job_id = job.get("id")
                if not job_id:
                    continue
                normalized.append(
                    {
                        "job_id": str(job_id),
                        "agent_name": job.get("agentId") or "",
                        "session_key": job.get("sessionKey") or "",
                        "enable": bool(job.get("enabled")),
                    }
                )

            def _write_once() -> None:
                db = app.state.db.database
                connect_db(db)
                try:
                    repo = JobSessionAgentRepository(db)
                    with db.atomic():
                        for j in normalized:
                            session_alias = None
                            if j["session_key"]:
                                sess = Session.get_or_none(Session.oc_session_key == j["session_key"])
                                if sess:
                                    session_alias = sess.session_alias

                            repo.upsert_by_job_id(
                                job_id=j["job_id"],
                                session_key=j["session_key"],
                                agent_name=j["agent_name"],
                                session_alias=session_alias,
                                enable=j["enable"],
                            )
                finally:
                    close_db(db)

            await run_in_threadpool(_write_once)
            await asyncio.sleep(60)

    asyncio.create_task(_load_official_skills_once())
    asyncio.create_task(_sync_oc_cron_jobs_forever())
    yield


from app.core.request_id_middleware import RequestIDMiddleware


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)
app.add_middleware(RequestIDMiddleware)
app.include_router(cc_router)
app.include_router(sandbox_router)
app.include_router(chat_base_router)
app.include_router(oc_base_router)
