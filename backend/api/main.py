"""FastAPI application entry point."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.schema import graphql_router
from backend.api.sse import router as sse_router
from backend.db.prompts import seed_default_prompts
from backend.db.session import async_session_factory

_LOCAL_NO_PROXY = "localhost,127.0.0.1,::1"


def _ensure_local_no_proxy() -> None:
    """Keep local DB/Qdrant/Redis traffic off system proxy."""
    for key in ("NO_PROXY", "no_proxy"):
        current = os.environ.get(key, "")
        missing = [h for h in _LOCAL_NO_PROXY.split(",") if h not in current]
        if missing:
            os.environ[key] = f"{current},{','.join(missing)}" if current else ",".join(missing)


_ensure_local_no_proxy()


def _run_migrations() -> None:
    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _run_migrations()
    async with async_session_factory() as session:
        await seed_default_prompts(session)
    yield


app = FastAPI(title="NL2SQL API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(graphql_router, prefix="/graphql")
app.include_router(sse_router)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
