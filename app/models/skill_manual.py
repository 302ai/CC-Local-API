from __future__ import annotations

import datetime
import hashlib

from peewee import AutoField, CharField, DateTimeField, TextField, BooleanField

from app.models.base import BaseModel

class SkillManualImport(BaseModel):
    id = AutoField()
    skill_name = CharField(max_length=64, unique=True)
    manual_import_time = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "skill_manual_import"
        indexes = (
            (('manual_import_time',), False),
        )
