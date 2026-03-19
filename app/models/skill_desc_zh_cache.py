from __future__ import annotations

import datetime

from peewee import AutoField, CharField, DateTimeField, TextField

from app.models.base import BaseModel


class SkillDescZhCache(BaseModel):
    id = AutoField()

    description_md5_16 = CharField(max_length=16, unique=True, index=True)
    description = TextField(null=True)
    description_zh = TextField(null=True)

    created_at = DateTimeField(default=datetime.datetime.utcnow)
    updated_at = DateTimeField(default=datetime.datetime.utcnow)

    class Meta:
        table_name = "skill_desc_zh_cache"

    def save(self, *args, **kwargs):
        self.updated_at = datetime.datetime.utcnow()
        return super().save(*args, **kwargs)
