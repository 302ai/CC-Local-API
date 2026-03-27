from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from peewee import SqliteDatabase

from app.models.base import bind_models
from app.models.skill_favorite import SkillFavorite


class SkillFavoriteRepository:
    def __init__(self, db: SqliteDatabase):
        self.db = db
        # 绑定模型到数据库
        bind_models(db, [SkillFavorite])

    def _ensure_tables(self) -> None:
        self.db.create_tables([SkillFavorite])

    @contextmanager
    def atomic(self) -> Iterator[None]:
        with self.db.atomic():
            yield

    def add(self, *, skill_name: str) -> bool:
        """
        添加收藏。
        由于 skill_name 设定了 unique=True，使用 on_conflict_ignore() 避免重复插入报错。
        返回 True 表示新增成功，False 表示已存在（未新增）。
        """
        self._ensure_tables()

        before = SkillFavorite.select().count()
        # 插入数据，favorite_time 由数据库默认值处理
        SkillFavorite.insert({SkillFavorite.skill_name: skill_name}).on_conflict_ignore().execute()
        after = SkillFavorite.select().count()

        return after > before

    def list(self) -> list[dict]:
        """
        获取所有收藏的技能名。
        按照收藏时间倒序排列（最新的在最前面）。
        """
        self._ensure_tables()

        q = (
            SkillFavorite
            .select(SkillFavorite.skill_name, SkillFavorite.favorite_time)
            .order_by(SkillFavorite.favorite_time.desc())  # 倒序：最新收藏的在前
        )
        return [
            {
                "skill_name": row.skill_name,
                "favorite_time": row.favorite_time,
            }
            for row in q
        ]

    def delete(self, *, skill_name: str) -> bool:
        """
        删除收藏（硬删除）。
        返回 True 表示删除成功，False 表示该技能本来就不存在。
        """
        self._ensure_tables()

        count = SkillFavorite.delete().where(SkillFavorite.skill_name == skill_name).execute()
        return count > 0
