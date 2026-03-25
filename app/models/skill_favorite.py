from __future__ import annotations

import datetime
import hashlib

from peewee import AutoField, CharField, DateTimeField, TextField, BooleanField

from app.models.base import BaseModel

class SkillFavorite(BaseModel):
    id = AutoField()
    skill_name = CharField(max_length=64, unique=True)
    favorite_time = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "skill_favorites"
        indexes = (
            (('favorite_time',), False),
        )
