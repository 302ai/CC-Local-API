from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import Callable, Generator, Iterator, TypeVar

from fastapi import Request
from peewee import SqliteDatabase

from app.db.database import connect_db, close_db

T = TypeVar("T")

_executor = ThreadPoolExecutor(max_workers=10)


async def run_in_threadpool(fn: Callable[[], T]) -> T:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, fn)


def get_db(request: Request) -> Generator[SqliteDatabase, None, None]:
    db: SqliteDatabase = request.app.state.db.database
    connect_db(db)
    try:
        yield db
    finally:
        close_db(db)


@contextmanager
def atomic(db: SqliteDatabase) -> Iterator[None]:
    with db.atomic() as _txn:
        yield
