"""Strawberry GraphQL schema and resolvers."""

import asyncio
import enum
import uuid
from typing import AsyncGenerator, Optional

import strawberry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from strawberry.fastapi import GraphQLRouter

from backend.api.admin_graphql import AdminMutationMixin, AdminQueryMixin, delete_datasource_cascade
from backend.api.session_manager import create_session, run_workflow, stream_events
from backend.cache.llm_cache import LlmCache
from backend.db.models import (
    Datasource,
    LlmCacheHitLog,
    RagAlert,
    SystemPrompt,
    TableMetadata,
)
from backend.db.prompts import activate_prompt_version, create_prompt_version, get_prompt_versions
from backend.db.session import async_session_factory
from backend.rag.indexer import IndexPipeline
from backend.workers.tasks import score_rag_chunks


async def get_db() -> AsyncSession:
    async with async_session_factory() as session:
        yield session


@strawberry.enum
class ExecutionMode(enum.Enum):
    AUTO = "AUTO"
    GENERATE_ONLY = "GENERATE_ONLY"
    EXECUTE = "EXECUTE"


@strawberry.enum
class StreamEventType(enum.Enum):
    STATUS = "STATUS"
    INTENT = "INTENT"
    RAG_CHUNK = "RAG_CHUNK"
    THOUGHT = "THOUGHT"
    LLM_TOKEN = "LLM_TOKEN"
    SQL = "SQL"
    RESULT = "RESULT"
    SUMMARY = "SUMMARY"
    ERROR = "ERROR"
    DONE = "DONE"


@strawberry.type
class Health:
    status: str
    version: str


@strawberry.type
class AskSessionType:
    session_id: str


@strawberry.type
class AskStreamEvent:
    event_type: StreamEventType
    data: strawberry.scalars.JSON


@strawberry.input
class AskInput:
    question: str
    datasource_id: int
    deep_think: bool = False
    execution_mode: ExecutionMode = ExecutionMode.AUTO


@strawberry.type
class DatasourceType:
    id: int
    name: str
    connection_url: str
    is_active: bool


@strawberry.type
class TableMetadataType:
    id: int
    table_name: str
    description: Optional[str]
    is_allowed: bool


@strawberry.type
class SystemPromptType:
    id: int
    role: str
    version: int
    content: str
    is_active: bool


@strawberry.type
class CacheStats:
    total_hits: int
    exact_hits: int
    semantic_hits: int
    total_tokens_saved: int


@strawberry.type
class CacheHitLogType:
    id: int
    session_id: Optional[str]
    hit_type: str
    saved_tokens: int
    similarity: Optional[float]
    latency_ms: int


@strawberry.type
class RagAlertType:
    id: int
    chunk_id: int
    question: str
    score: float
    is_resolved: bool


@strawberry.input
class CreatePromptInput:
    role: str
    content: str
    activate: bool = True


@strawberry.input
class CreateDatasourceInput:
    name: str
    connection_url: str
    is_active: bool = True


@strawberry.input
class UpdateDatasourceInput:
    id: int
    name: Optional[str] = None


@strawberry.type
class Query(AdminQueryMixin):
    @strawberry.field
    async def health(self) -> Health:
        return Health(status="ok", version="0.1.0")

    @strawberry.field
    async def datasources(self) -> list[DatasourceType]:
        async with async_session_factory() as session:
            result = await session.execute(select(Datasource))
            return [
                DatasourceType(
                    id=ds.id,
                    name=ds.name,
                    connection_url=ds.connection_url,
                    is_active=ds.is_active,
                )
                for ds in result.scalars().all()
            ]

    @strawberry.field
    async def tables(self, datasource_id: int) -> list[TableMetadataType]:
        async with async_session_factory() as session:
            result = await session.execute(
                select(TableMetadata).where(TableMetadata.datasource_id == datasource_id)
            )
            return [
                TableMetadataType(
                    id=t.id,
                    table_name=t.table_name,
                    description=t.description,
                    is_allowed=t.is_allowed,
                )
                for t in result.scalars().all()
            ]

    @strawberry.field
    async def prompts(self, role: Optional[str] = None) -> list[SystemPromptType]:
        async with async_session_factory() as session:
            q = select(SystemPrompt)
            if role:
                q = q.where(SystemPrompt.role == role)
            result = await session.execute(q.order_by(SystemPrompt.role, SystemPrompt.version.desc()))
            return [
                SystemPromptType(
                    id=p.id,
                    role=p.role,
                    version=p.version,
                    content=p.content,
                    is_active=p.is_active,
                )
                for p in result.scalars().all()
            ]

    @strawberry.field
    async def prompt_versions(self, role: str) -> list[SystemPromptType]:
        async with async_session_factory() as session:
            versions = await get_prompt_versions(session, role)
            return [
                SystemPromptType(
                    id=p.id,
                    role=p.role,
                    version=p.version,
                    content=p.content,
                    is_active=p.is_active,
                )
                for p in versions
            ]

    @strawberry.field
    async def cache_stats(self) -> CacheStats:
        async with async_session_factory() as session:
            stats = await LlmCache(session).get_stats()
            return CacheStats(**stats)

    @strawberry.field
    async def cache_hit_logs(self, limit: int = 50) -> list[CacheHitLogType]:
        async with async_session_factory() as session:
            result = await session.execute(
                select(LlmCacheHitLog).order_by(LlmCacheHitLog.created_at.desc()).limit(limit)
            )
            return [
                CacheHitLogType(
                    id=log.id,
                    session_id=log.session_id,
                    hit_type=log.hit_type,
                    saved_tokens=log.saved_tokens,
                    similarity=log.similarity,
                    latency_ms=log.latency_ms,
                )
                for log in result.scalars().all()
            ]

    @strawberry.field
    async def rag_alerts(self, resolved: Optional[bool] = None) -> list[RagAlertType]:
        async with async_session_factory() as session:
            q = select(RagAlert)
            if resolved is not None:
                q = q.where(RagAlert.is_resolved == resolved)
            result = await session.execute(q.order_by(RagAlert.created_at.desc()))
            return [
                RagAlertType(
                    id=a.id,
                    chunk_id=a.chunk_id,
                    question=a.question,
                    score=a.score,
                    is_resolved=a.is_resolved,
                )
                for a in result.scalars().all()
            ]


@strawberry.type
class Mutation(AdminMutationMixin):
    @strawberry.mutation
    async def ask_question(self, input: AskInput) -> AskSessionType:
        session_id = str(uuid.uuid4())
        create_session(session_id, question=input.question)

        initial_state = {
            "session_id": session_id,
            "question": input.question,
            "deep_think": input.deep_think,
            "execution_mode": input.execution_mode.value,
            "datasource_id": input.datasource_id,
            "stream_events": [],
        }

        async def _run():
            async with async_session_factory() as db_session:
                await run_workflow(session_id, initial_state, db_session)

        asyncio.create_task(_run())
        return AskSessionType(session_id=session_id)

    @strawberry.mutation
    async def create_datasource(self, input: CreateDatasourceInput) -> DatasourceType:
        async with async_session_factory() as session:
            ds = Datasource(
                name=input.name.strip(),
                connection_url=input.connection_url.strip(),
                is_active=input.is_active,
            )
            session.add(ds)
            await session.commit()
            await session.refresh(ds)
            return DatasourceType(
                id=ds.id,
                name=ds.name,
                connection_url=ds.connection_url,
                is_active=ds.is_active,
            )

    @strawberry.mutation
    async def update_datasource(self, input: UpdateDatasourceInput) -> Optional[DatasourceType]:
        async with async_session_factory() as session:
            ds = await session.get(Datasource, input.id)
            if not ds:
                return None
            if input.name is not None:
                name = input.name.strip()
                if not name:
                    raise ValueError("数据源名称不能为空")
                ds.name = name
            await session.commit()
            await session.refresh(ds)
            return DatasourceType(
                id=ds.id,
                name=ds.name,
                connection_url=ds.connection_url,
                is_active=ds.is_active,
            )

    @strawberry.mutation
    async def delete_datasource(self, datasource_id: int) -> bool:
        async with async_session_factory() as session:
            ok = await delete_datasource_cascade(session, datasource_id)
            if ok:
                await session.commit()
            return ok

    @strawberry.mutation
    async def create_prompt(self, input: CreatePromptInput) -> SystemPromptType:
        async with async_session_factory() as session:
            prompt = await create_prompt_version(
                session, input.role, input.content, input.activate
            )
            return SystemPromptType(
                id=prompt.id,
                role=prompt.role,
                version=prompt.version,
                content=prompt.content,
                is_active=prompt.is_active,
            )

    @strawberry.mutation
    async def activate_prompt(self, prompt_id: int) -> Optional[SystemPromptType]:
        async with async_session_factory() as session:
            prompt = await activate_prompt_version(session, prompt_id)
            if not prompt:
                return None
            return SystemPromptType(
                id=prompt.id,
                role=prompt.role,
                version=prompt.version,
                content=prompt.content,
                is_active=prompt.is_active,
            )

    @strawberry.mutation
    async def index_datasource(self, datasource_id: int) -> int:
        async with async_session_factory() as session:
            pipeline = IndexPipeline(session)
            return await pipeline.index_all_for_datasource(datasource_id)

    @strawberry.mutation
    async def resolve_alert(self, alert_id: int) -> bool:
        async with async_session_factory() as session:
            alert = await session.get(RagAlert, alert_id)
            if not alert:
                return False
            alert.is_resolved = True
            await session.commit()
            return True


@strawberry.type
class Subscription:
    @strawberry.subscription
    async def ask_stream(self, session_id: str) -> AsyncGenerator[AskStreamEvent, None]:
        async for event in stream_events(session_id):
            event_type_str = event.get("type", "STATUS")
            try:
                event_type = StreamEventType[event_type_str]
            except KeyError:
                event_type = StreamEventType.STATUS
            yield AskStreamEvent(event_type=event_type, data=event.get("data", {}))

            if event_type_str == "RAG_CHUNK":
                from backend.api.session_manager import get_session

                ask_session = get_session(session_id)
                chunks = event.get("data", {}).get("chunks", [])
                if chunks and ask_session:
                    score_rag_chunks.delay(
                        question=ask_session.question,
                        chunks=chunks,
                        session_id=session_id,
                    )


schema = strawberry.Schema(query=Query, mutation=Mutation, subscription=Subscription)
graphql_router = GraphQLRouter(schema)
