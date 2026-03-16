from __future__ import annotations

from peewee import AutoField, BigIntegerField, CharField

from app.models.base import BaseModel


class JobSyncLog(BaseModel):
    id = AutoField()
    job_id = CharField(max_length=64, index=True)
    ts = BigIntegerField(index=True)

    class Meta:
        table_name = "job_sync_logs"
        indexes = ((('job_id', 'ts'), True),)
