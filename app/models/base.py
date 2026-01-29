from __future__ import annotations

from peewee import Model


def bind_models(database, models: list[type[Model]]) -> None:
    for m in models:
        m._meta.database = database


class BaseModel(Model):
    class Meta:
        database = None  # 运行时绑定
