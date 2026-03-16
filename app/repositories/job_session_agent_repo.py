from __future__ import annotations

import datetime
from contextlib import contextmanager
from typing import Iterator, Optional

from peewee import SqliteDatabase

from app.models.base import bind_models
from app.models.job_session_agent import JobSessionAgent


class JobSessionAgentRepository:
    def __init__(self, db: SqliteDatabase):
        self.db = db
        bind_models(db, [JobSessionAgent])

    def _ensure_tables(self) -> None:
        self.db.create_tables([JobSessionAgent])

    def upsert_by_job_id(
        self,
        *,
        job_id: str,
        session_key: str,
        agent_name: str,
        session_alias: str | None,
        enable: bool,
    ) -> JobSessionAgent:
        self._ensure_tables()

        row = (
            JobSessionAgent.select()
            .where(JobSessionAgent.job_id == job_id)
            .order_by(JobSessionAgent.id.desc())
            .first()
        )

        if row:
            row.session_key = session_key
            row.agent_name = agent_name
            row.session_alias = session_alias
            row.enable = enable
            row.save()
            return row

        now = datetime.datetime.utcnow()
        return JobSessionAgent.create(
            job_id=job_id,
            session_key=session_key,
            agent_name=agent_name,
            session_alias=session_alias,
            enable=enable,
            created_at=now,
            updated_at=now,
        )

    @contextmanager
    def atomic(self) -> Iterator[None]:
        with self.db.atomic():
            yield

    def create(
        self,
        *,
        job_id: str,
        session_key: str,
        agent_name: str,
        session_alias: str | None = None,
        enable: bool = True,
    ) -> JobSessionAgent:
        self._ensure_tables()

        now = datetime.datetime.utcnow()
        return JobSessionAgent.create(
            job_id=job_id,
            session_key=session_key,
            agent_name=agent_name,
            session_alias=session_alias,
            enable=enable,
            created_at=now,
            updated_at=now,
        )

    def update(
        self,
        id: int,
        *,
        job_id: str | None = ...,
        session_key: str | None = ...,
        agent_name: str | None = ...,
        session_alias: str | None = ...,
        enable: bool | None = ...,
    ) -> Optional[JobSessionAgent]:
        self._ensure_tables()

        row = JobSessionAgent.get_or_none(JobSessionAgent.id == id)
        if not row:
            return None

        if job_id is not ...:
            row.job_id = job_id
        if session_key is not ...:
            row.session_key = session_key
        if agent_name is not ...:
            row.agent_name = agent_name
        if session_alias is not ...:
            row.session_alias = session_alias
        if enable is not ...:
            row.enable = enable

        row.save()
        return row

    def get(self, id: int) -> Optional[JobSessionAgent]:
        self._ensure_tables()
        return JobSessionAgent.get_or_none(JobSessionAgent.id == id)

    def find_enabled(
        self,
        *,
        job_id: str | None = None,
        session_key: str | None = None,
        agent_name: str | None = None,
        session_alias: str | None = None,
    ) -> list[JobSessionAgent]:
        self._ensure_tables()

        q = JobSessionAgent.select().where(JobSessionAgent.enable == True)  # noqa: E712
        if job_id:
            q = q.where(JobSessionAgent.job_id == job_id)
        if session_key:
            q = q.where(JobSessionAgent.session_key == session_key)
        if agent_name:
            q = q.where(JobSessionAgent.agent_name == agent_name)
        if session_alias:
            q = q.where(JobSessionAgent.session_alias == session_alias)

        return list(q.order_by(JobSessionAgent.id.desc()))

    def list_by_session_alias(
        self,
        *,
        session_alias: str,
    ) -> list[JobSessionAgent]:
        self._ensure_tables()

        return list(
            JobSessionAgent.select()
            .where(JobSessionAgent.session_alias == session_alias)
            .order_by(JobSessionAgent.id.desc())
        )

    def disable(self, id: int) -> bool:
        self._ensure_tables()
        rows = (
            JobSessionAgent
            .update({JobSessionAgent.enable: False, JobSessionAgent.updated_at: datetime.datetime.utcnow()})
            .where(JobSessionAgent.id == id)
            .execute()
        )
        return rows > 0
