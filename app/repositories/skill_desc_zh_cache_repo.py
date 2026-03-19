from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

from peewee import SqliteDatabase

from app.models.base import bind_models
from app.models.skill_desc_zh_cache import SkillDescZhCache


class SkillDescZhCacheRepository:
    def __init__(self, db: SqliteDatabase):
        self.db = db
        bind_models(db, [SkillDescZhCache])

    def _ensure_tables(self) -> None:
        self.db.create_tables([SkillDescZhCache])

    @contextmanager
    def atomic(self) -> Iterator[None]:
        with self.db.atomic() as _txn:
            yield

    def get_by_md5_16(self, description_md5_16: str) -> Optional[SkillDescZhCache]:
        self._ensure_tables()
        return SkillDescZhCache.get_or_none(SkillDescZhCache.description_md5_16 == description_md5_16)

    def upsert(
        self,
        *,
        description_md5_16: str,
        description: str,
        description_zh: str,
    ) -> SkillDescZhCache:
        self._ensure_tables()

        (SkillDescZhCache
         .insert(
            description_md5_16=description_md5_16,
            description=description,
            description_zh=description_zh,
         )
         .on_conflict(
            conflict_target=[SkillDescZhCache.description_md5_16],
            update={
                SkillDescZhCache.description: description,
                SkillDescZhCache.description_zh: description_zh,
            },
         )
         .execute())

        return SkillDescZhCache.get(SkillDescZhCache.description_md5_16 == description_md5_16)
