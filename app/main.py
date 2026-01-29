from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import cc_router, sandbox_router
from app.core.config import settings
from app.db.database import db_state_default
from app.models.base import bind_models
from app.models.skill import Skill
from app.models.session import Session


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = db_state_default()
    bind_models(app.state.db.database, [Skill, Session])
    yield


from app.core.request_id_middleware import RequestIDMiddleware


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)
app.add_middleware(RequestIDMiddleware)
app.include_router(cc_router)
app.include_router(sandbox_router)
