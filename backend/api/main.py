"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.schema import graphql_router
from backend.api.sse import router as sse_router
from backend.db.prompts import seed_default_prompts
from backend.db.session import async_session_factory


@asynccontextmanager
async def lifespan(app: FastAPI):
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
