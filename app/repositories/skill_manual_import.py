from __future__ import annotations

import datetime
from contextlib import contextmanager
from typing import Iterator

from peewee import SqliteDatabase, EXCLUDED

from app.models.base import bind_models
from app.models.skill_manual import SkillManualImport

class SkillManualImportRepository:
    def __init__(self, db: SqliteDatabase):
        self.db = db
        # 绑定模型到数据库
        bind_models(db, [SkillManualImport])

    def _ensure_tables(self) -> None:
        self.db.create_tables([SkillManualImport])

    @contextmanager
    def atomic(self) -> Iterator[None]:
        with self.db.atomic():
            yield

    import datetime

    def upsert(self, *, skill_name: str) -> bool:
        """
        添加或更新收藏。
        skill_name 不存在则插入，已存在则更新 manual_import_time。
        返回 True 表示新增，False 表示已存在（仅更新了时间）。
        """
        self._ensure_tables()

        now = datetime.datetime.now()

        # 尝试查找已有记录
        existing = (
            SkillManualImport
            .select()
            .where(SkillManualImport.skill_name == skill_name)
            .first()
        )

        if existing:
            # 已存在，更新时间
            (
                SkillManualImport
                .update({SkillManualImport.manual_import_time: now})
                .where(SkillManualImport.skill_name == skill_name)
                .execute()
            )
            return False
        else:
            # 不存在，插入
            SkillManualImport.create(
                skill_name=skill_name,
                manual_import_time=now,
            )
            return True

    def list(self) -> list[dict]:
        """
        获取所有收藏的技能。
        按照收藏时间倒序排列（最新的在最前面）。
        返回包含 skill_name 和 manual_import_time 的字典列表。
        """
        self._ensure_tables()

        q = (
            SkillManualImport
            .select(SkillManualImport.skill_name, SkillManualImport.manual_import_time)
            .order_by(SkillManualImport.manual_import_time.desc())
        )
        return [
            {
                "skill_name": row.skill_name,
                "manual_import_time": row.manual_import_time,
            }
            for row in q
        ]

    def delete(self, *, skill_name: str) -> bool:
        """
        删除收藏（硬删除）。
        返回 True 表示删除成功，False 表示该技能本来就不存在。
        """
        self._ensure_tables()

        count = SkillManualImport.delete().where(SkillManualImport.skill_name == skill_name).execute()
        return count > 0
