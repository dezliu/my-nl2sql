"""Shared fixtures for API and service tests (SQLite in-memory, no LLM/Qdrant)."""

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import backend.db.models  # noqa: F401 — register all tables on Base.metadata
from backend.db.models import BusinessGlossary, Datasource, KnowledgeEntry, SqlTemplate, TableMetadata
from backend.db.session import Base

SESSION_FACTORY_PATCH_TARGETS = [
    "backend.db.session.async_session_factory",
    "backend.api.schema.async_session_factory",
    "backend.api.admin_graphql.async_session_factory",
    "backend.api.main.async_session_factory",
    "backend.api.sse.async_session_factory",
]


@pytest_asyncio.fixture
async def test_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def test_session_factory(test_engine):
    return async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def patch_db(test_session_factory, monkeypatch):
    for target in SESSION_FACTORY_PATCH_TARGETS:
        monkeypatch.setattr(target, test_session_factory)
    yield test_session_factory


@pytest_asyncio.fixture
async def seeded_db(patch_db):
    async with patch_db() as session:
        ds = Datasource(
            name="Test DS",
            connection_url="mysql://user:pass@localhost:3306/testdb",
            is_active=True,
        )
        session.add(ds)
        await session.flush()

        users = TableMetadata(
            datasource_id=ds.id,
            table_name="users",
            description="用户表",
            is_allowed=True,
        )
        session.add(users)
        await session.flush()

        term = BusinessGlossary(term="GMV", definition="成交总额")
        session.add(term)

        tpl = SqlTemplate(
            datasource_id=ds.id,
            question="count users",
            sql_text="SELECT COUNT(*) FROM users",
        )
        session.add(tpl)

        entry = KnowledgeEntry(
            title="FAQ",
            content="How to query users",
            category="faq",
            datasource_id=ds.id,
        )
        session.add(entry)

        await session.commit()
        await session.refresh(ds)
        await session.refresh(users)
        await session.refresh(term)
        await session.refresh(tpl)
        await session.refresh(entry)

        yield {
            "datasource": ds,
            "table": users,
            "glossary": term,
            "template": tpl,
            "knowledge": entry,
        }


@pytest_asyncio.fixture
async def client(patch_db):
    from backend.api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def gql(client: AsyncClient, query: str, variables: dict | None = None) -> dict:
    response = await client.post(
        "/graphql",
        json={"query": query, "variables": variables or {}},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    if body.get("errors"):
        raise AssertionError(f"GraphQL errors: {body['errors']}")
    return body["data"]


@pytest.fixture
def mock_run_workflow():
    async def _fake_run_workflow(
        session_id: str,
        initial_state: dict,
        db_session,
        event_emitter=None,
    ) -> None:
        if event_emitter:
            await event_emitter("INTENT", {"intent": "query_data"})
            await event_emitter("LLM_TOKEN", {"role": "summary", "delta": "测试"})
            await event_emitter("SUMMARY", {"text": "测试总结"})
            await event_emitter("DONE", {"session_id": session_id})

    with patch("backend.api.sse.run_workflow", side_effect=_fake_run_workflow), patch(
        "backend.api.schema.run_workflow", side_effect=_fake_run_workflow
    ):
        yield _fake_run_workflow


@pytest.fixture
def mock_retriever():
    from backend.rag.retriever import RetrievedChunk

    chunks = [
        RetrievedChunk(
            chunk_id="1",
            content="Table: users\nColumns: id INT",
            score=0.9,
            doc_type="table_metadata",
            metadata={},
        )
    ]

    with patch("backend.api.admin_graphql.HybridRetriever") as mock_cls:
        mock_cls.return_value.search.return_value = chunks
        yield mock_cls


@pytest.fixture
def mock_index_pipeline():
    with patch("backend.rag.index_ops.IndexPipeline") as mock_cls:
        instance = mock_cls.return_value
        instance.index_table = AsyncMock(return_value=True)
        instance.index_template = AsyncMock(return_value=True)
        instance.index_glossary_term = AsyncMock(return_value=True)
        instance.index_fk = AsyncMock(return_value=True)
        instance.index_knowledge = AsyncMock(return_value=True)
        instance.unindex_by_source = AsyncMock(return_value=True)
        yield mock_cls
