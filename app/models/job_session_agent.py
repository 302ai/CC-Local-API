from __future__ import annotations

import datetime

from peewee import AutoField, BooleanField, CharField, DateTimeField

from app.models.base import BaseModel


class JobSessionAgent(BaseModel):
    id = AutoField()

    job_id = CharField(max_length=64, index=True)
    session_key = CharField(max_length=128, null=True, index=True)
    agent_name = CharField(max_length=128, null=True, index=True)
    session_alias = CharField(max_length=255, null=True, index=True)

    enable = BooleanField(default=True, index=True)

    created_at = DateTimeField(default=datetime.datetime.utcnow)
    updated_at = DateTimeField(default=datetime.datetime.utcnow)

    class Meta:
        table_name = "job_session_agents"

    def save(self, *args, **kwargs):
        self.updated_at = datetime.datetime.utcnow()
        return super().save(*args, **kwargs)
