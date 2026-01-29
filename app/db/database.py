from __future__ import annotations

from dataclasses import dataclass

from peewee import SqliteDatabase

from app.core.config import settings


@dataclass
class DBState:
    database: SqliteDatabase


def create_database() -> SqliteDatabase:
    from pathlib import Path
    db_path = Path(settings.DB_SQLITE_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    return SqliteDatabase(
        settings.DB_SQLITE_PATH,
        pragmas={
            "journal_mode": "wal",
            "cache_size": -1024 * 64,
            "foreign_keys": 1,
        },
        check_same_thread=False,
    )


def db_state_default() -> DBState:
    return DBState(database=create_database())


def connect_db(db: SqliteDatabase) -> None:
    if db.is_closed():
        db.connect(reuse_if_open=True)


def close_db(db: SqliteDatabase) -> None:
    if not db.is_closed():
        db.close()


def reconnect_db(db: SqliteDatabase) -> None:
    try:
        if not db.is_closed():
            db.close()
    finally:
        db.connect(reuse_if_open=True)
