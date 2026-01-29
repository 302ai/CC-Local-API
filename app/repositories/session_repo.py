from __future__ import annotations

import datetime
from contextlib import contextmanager
from typing import Iterator, Optional, NamedTuple

from peewee import SqliteDatabase

from app.models.session import Session


class SessionListResult(NamedTuple):
    items: list[Session]
    total: int


class SessionRepository:
    def __init__(self, db: SqliteDatabase):
        self.db = db

    def _ensure_tables(self) -> None:
        self.db.create_tables([Session])

    @contextmanager
    def atomic(self) -> Iterator[None]:
        with self.db.atomic():
            yield

    def create_session(
            self,
            *,
            session_id: str | None = None,
            session_alias: str | None = None,
            note: str | None = None,
            workspace_path: str | None = None,
    ) -> Session:
        """创建新会话"""
        self._ensure_tables()

        now = datetime.datetime.utcnow()

        return Session.create(
            session_id=session_id,
            session_alias=session_alias,
            note=note,
            workspace_path=workspace_path,
            last_used_at=now,
            created_at=now,
            updated_at=now,
        )

    def update_session(
            self,
            id: int,
            *,
            session_id: str | None = ...,  # 使用 ... 区分 None 和未传参
            session_alias: str | None = ...,
            note: str | None = ...,
            workspace_path: str | None = ...,
    ) -> Optional[Session]:
        """更新会话信息"""
        self._ensure_tables()

        session = Session.get_or_none(Session.id == id)
        if not session:
            return None

        if session_id is not ...:
            session.session_id = session_id
        if session_alias is not ...:
            session.session_alias = session_alias
        if note is not ...:
            session.note = note
        if workspace_path is not ...:
            session.workspace_path = workspace_path

        session.save()
        return session

    def bind_session_id(self, id: int, session_id: str) -> Optional[Session]:
        """为已有会话绑定 session_id"""
        self._ensure_tables()

        session = Session.get_or_none(Session.id == id)
        if not session:
            return None

        session.session_id = session_id
        session.last_used_at = datetime.datetime.utcnow()
        session.save()
        return session

    def get_session(self, id: int) -> Optional[Session]:
        """通过主键 id 获取会话"""
        self._ensure_tables()
        return Session.get_or_none(Session.id == id)

    def get_session_by_session_id(self, session_id: str) -> Optional[Session]:
        """通过 session_id 获取会话"""
        self._ensure_tables()
        if not session_id:
            return None
        return Session.get_or_none(Session.session_id == session_id)

    def get_session_by_alias(self, alias: str) -> Optional[Session]:
        """通过别名查询会话"""
        self._ensure_tables()
        if not alias:
            return None
        return Session.get_or_none(Session.session_alias == alias)

    def list_sessions(
            self,
            *,
            q: str | None = None,
            workspace_path: str | None = None,
            has_session_id: bool | None = None,
            limit: int = 50,
            offset: int = 0,
    ) -> SessionListResult:
        """
        获取会话列表，默认按最后使用时间倒序排列

        :param q: 模糊搜索（别名或备注）
        :param workspace_path: 按工作区路径筛选
        :param has_session_id: True=已绑定, False=未绑定, None=全部
        :param limit: 分页大小
        :param offset: 偏移量
        """
        self._ensure_tables()

        base = Session.select()

        if q:
            base = base.where(
                (Session.session_alias.contains(q)) |
                (Session.note.contains(q))
            )
        if workspace_path:
            base = base.where(Session.workspace_path == workspace_path)
        if has_session_id is True:
            base = base.where(Session.session_id.is_null(False))
        elif has_session_id is False:
            base = base.where(Session.session_id.is_null(True))

        total = base.count()
        items = list(
            base
            .order_by(Session.last_used_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return SessionListResult(items=items, total=total)

    def touch_session(self, id: int) -> Optional[Session]:
        """更新会话的最后使用时间"""
        self._ensure_tables()

        session = Session.get_or_none(Session.id == id)
        if not session:
            return None

        session.last_used_at = datetime.datetime.utcnow()
        session.save()
        return session

    def delete_session(self, id: int) -> bool:
        """删除会话"""
        self._ensure_tables()
        rows = Session.delete().where(Session.id == id).execute()
        return rows > 0
