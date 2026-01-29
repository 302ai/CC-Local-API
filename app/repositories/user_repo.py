from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

from peewee import SqliteDatabase

from app.models import User


class UserRepository:
    def __init__(self, db: SqliteDatabase):
        self.db = db

    @contextmanager
    def atomic(self) -> Iterator[None]:
        # 业务可选事务边界
        with self.db.atomic() as _txn:
            yield

    def create_user(self, name: str) -> User:
        self.db.create_tables([User])
        return User.create(name=name)

    def get_user(self, user_id: int) -> Optional[User]:
        self.db.create_tables([User])
        return User.get_or_none(User.id == user_id)
