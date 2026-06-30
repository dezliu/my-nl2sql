"""Tests for metadata sync service."""

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import backend.db.models  # noqa: F401
from backend.db.models import ColumnMetadata, Datasource, FkRelationship, TableMetadata
from backend.db.session import Base
from backend.services.metadata_sync import (
    SyncMetadataOptions,
    SyncTableItem,
    sync_datasource_metadata,
)
from backend.services.schema_introspector import (
    IntrospectionResult,
    ScannedColumn,
    ScannedForeignKey,
    ScannedTable,
)


@pytest_asyncio.fixture
async def sync_session():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        ds = Datasource(
            name="Remote",
            connection_url="mysql://u:p@localhost:3306/demo",
            is_active=True,
        )
        session.add(ds)
        await session.flush()

        existing = TableMetadata(
            datasource_id=ds.id,
            table_name="users",
            description="人工描述",
            is_allowed=True,
        )
        session.add(existing)
        await session.flush()
        session.add(
            ColumnMetadata(
                table_id=existing.id,
                column_name="id",
                data_type="INT",
                description="主键备注",
            )
        )
        await session.commit()
        await session.refresh(ds)
        yield session, ds.id
    await engine.dispose()


def _intro() -> IntrospectionResult:
    return IntrospectionResult(
        tables=[
            ScannedTable(
                table_name="users",
                table_comment="远程注释",
                columns=[
                    ScannedColumn("id", "int", "远程列注释"),
                    ScannedColumn("username", "varchar(64)", None),
                ],
            ),
            ScannedTable(
                table_name="orders",
                table_comment="订单",
                columns=[
                    ScannedColumn("id", "int", None),
                    ScannedColumn("user_id", "int", None),
                ],
            ),
        ],
        foreign_keys=[
            ScannedForeignKey("orders", "user_id", "users", "id"),
        ],
    )


@pytest.mark.asyncio
async def test_sync_preserves_existing_descriptions(sync_session):
    session, ds_id = sync_session
    result = await sync_datasource_metadata(
        session,
        ds_id,
        "mysql://u:p@localhost:3306/demo",
        [SyncTableItem("users"), SyncTableItem("orders", description="新订单表")],
        SyncMetadataOptions(sync_fks=True, index_to_rag=False),
        introspection=_intro(),
    )

    assert result.tables_updated == 1
    assert result.tables_added == 1
    assert result.columns_added >= 2
    assert result.fks_synced == 1

    users = (
        await session.execute(
            select(TableMetadata).where(
                TableMetadata.datasource_id == ds_id,
                TableMetadata.table_name == "users",
            )
        )
    ).scalar_one()
    assert users.description == "人工描述"

    col = (
        await session.execute(
            select(ColumnMetadata).where(
                ColumnMetadata.table_id == users.id,
                ColumnMetadata.column_name == "id",
            )
        )
    ).scalar_one()
    assert col.description == "主键备注"

    orders = (
        await session.execute(
            select(TableMetadata).where(TableMetadata.table_name == "orders")
        )
    ).scalar_one()
    assert orders.description == "新订单表"

    fk_count = (
        await session.execute(
            select(FkRelationship).where(FkRelationship.datasource_id == ds_id)
        )
    ).scalars().all()
    assert len(fk_count) == 1


@pytest.mark.asyncio
async def test_sync_skips_fk_when_target_table_not_selected(sync_session):
    session, ds_id = sync_session
    result = await sync_datasource_metadata(
        session,
        ds_id,
        "mysql://u:p@localhost:3306/demo",
        [SyncTableItem("orders")],
        SyncMetadataOptions(sync_fks=True),
        introspection=_intro(),
    )
    assert result.fks_synced == 0
    assert any("目标表未同步" in e for e in result.errors)
