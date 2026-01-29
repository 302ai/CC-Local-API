from __future__ import annotations

import datetime
from contextlib import contextmanager
from typing import Iterator, Optional, NamedTuple

from peewee import SqliteDatabase

from app.models.skill import Skill

class SkillListResult(NamedTuple):
    items: list[Skill]
    total: int

class SkillRepository:
    def __init__(self, db: SqliteDatabase):
        self.db = db

    def _ensure_tables(self) -> None:
        self.db.create_tables([Skill])

    @contextmanager
    def atomic(self) -> Iterator[None]:
        with self.db.atomic() as _txn:
            yield

    def upsert_skill(
            self,
            *,
            name: str,
            skill_type: str,
            source_url_hash: str,
            source_url: str,
            description_en: str | None = None,
            description_zh: str | None = None,
            local_path: str | None = None,
    ) -> Skill:
        self._ensure_tables()

        now = datetime.datetime.utcnow()

        insert_data = dict(
            name=name,
            skill_type=skill_type,
            description_en=description_en,
            description_zh=description_zh,
            source_url=source_url,
            source_url_hash=source_url_hash,
            local_path=local_path,
            created_at=now,
            updated_at=now,
        )

        # 冲突时要更新的字段（通常不更新 created_at）
        update_data = dict(
            skill_type=skill_type,
            description_en=description_en,
            description_zh=description_zh,
            source_url=source_url,
            local_path=local_path,
            updated_at=now,
        )

        # 如果你不想用 None 覆盖旧值，可以过滤 None：
        update_data = {k: v for k, v in update_data.items() if v is not None}
        update_data["updated_at"] = now  # 确保 updated_at 一定更新

        (Skill
         .insert(**insert_data)
         .on_conflict(
            conflict_target=[Skill.name, Skill.source_url_hash],
            update=update_data,
        )
         .execute())

        # 返回最终记录
        return Skill.get(
            (Skill.name == name) & (Skill.source_url_hash == source_url_hash)
        )

    def get_skill(self, skill_id: int) -> Optional[Skill]:
        self._ensure_tables()
        return Skill.get_or_none(Skill.id == skill_id)

    def get_skill_by_name(self, name: str) -> Optional[Skill]:
        self._ensure_tables()
        return (Skill
                .select()
                .where(Skill.name == name)
                .order_by(Skill.id.desc())
                .first())

    def list_skills(
            self,
            *,
            skill_type: str | None = None,
            q: str | None = None,
            limit: int = 50,
            offset: int = 0,
    ) -> SkillListResult:
        self._ensure_tables()
        base = Skill.select()
        if skill_type:
            base = base.where(Skill.skill_type == skill_type)
        if q:
            base = base.where(Skill.name.contains(q))

        total = base.count()
        items = list(base.order_by(Skill.id.desc()).limit(limit).offset(offset))
        return SkillListResult(items=items, total=total)

    def update_skill(
        self,
        skill_id: int,
        *,
        name: str | None = None,
        skill_type: str | None = None,
        description_en: str | None = None,
        description_zh: str | None = None,
        source_url: str | None = None,
        local_path: str | None = None,
    ) -> Optional[Skill]:
        self._ensure_tables()

        skill = Skill.get_or_none(Skill.id == skill_id)
        if not skill:
            return None

        if name is not None:
            skill.name = name
        if skill_type is not None:
            skill.skill_type = skill_type
        if description_en is not None:
            skill.description_en = description_en
        if description_zh is not None:
            skill.description_zh = description_zh
        if source_url is not None:
            skill.source_url = source_url
        if local_path is not None:
            skill.local_path = local_path

        skill.save()
        return skill

    def delete_skill(self, skill_id: int) -> bool:
        self._ensure_tables()
        rows = Skill.delete().where(Skill.id == skill_id).execute()
        return rows > 0
