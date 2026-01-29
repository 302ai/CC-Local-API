from __future__ import annotations

import datetime
import hashlib

from peewee import AutoField, CharField, DateTimeField, TextField, BooleanField

from app.models.base import BaseModel


class Skill(BaseModel):
    id = AutoField()

    name = CharField(index=True)
    skill_type = CharField(default='', index=True)  # 允许空字符串

    description_en = TextField(null=True)
    description_zh = TextField(null=True)

    source_url = TextField(null=True)
    source_url_hash = CharField(max_length=64, null=True, index=True)

    local_path = TextField(null=True)

    is_collected = BooleanField(default=False)

    created_at = DateTimeField(default=datetime.datetime.utcnow)
    updated_at = DateTimeField(default=datetime.datetime.utcnow)

    class Meta:
        table_name = "skills"
        indexes = (
            (("skill_type",), False),
            # name 和 source_url_hash 联合唯一索引
            (("name", "source_url_hash"), True),
        )

    def save(self, *args, **kwargs):
        self.updated_at = datetime.datetime.utcnow()
        return super().save(*args, **kwargs)
