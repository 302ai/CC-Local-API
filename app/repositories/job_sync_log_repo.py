from __future__ import annotations

from peewee import SqliteDatabase

from app.models.base import bind_models
from app.models.job_sync_log import JobSyncLog


class JobSyncLogRepository:
    def __init__(self, db: SqliteDatabase):
        self.db = db
        bind_models(db, [JobSyncLog])

    def _ensure_tables(self) -> None:
        self.db.create_tables([JobSyncLog])

    def insert(self, *, job_id: str, ts: int) -> bool:
        self._ensure_tables()

        before = JobSyncLog.select().count()
        JobSyncLog.insert({JobSyncLog.job_id: job_id, JobSyncLog.ts: ts}).on_conflict_ignore().execute()
        after = JobSyncLog.select().count()
        return after > before

    def list_ts_by_job_id(self, job_id: str) -> list[int]:
        self._ensure_tables()

        q = (
            JobSyncLog
            .select(JobSyncLog.ts)
            .where(JobSyncLog.job_id == job_id)
            .order_by(JobSyncLog.ts.asc())
        )
        return [row.ts for row in q]
