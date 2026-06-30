"""Sync remote MySQL schema into local metadata tables."""

from dataclasses import dataclass, field

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import ColumnMetadata, FkRelationship, TableMetadata
from backend.rag.indexer import IndexPipeline
from backend.services.schema_introspector import (
    IntrospectionResult,
    ScannedTable,
    introspect_mysql,
)


@dataclass
class SyncTableItem:
    table_name: str
    description: str | None = None
    is_allowed: bool = True


@dataclass
class SyncMetadataOptions:
    sync_fks: bool = True
    index_to_rag: bool = False


@dataclass
class SyncResult:
    tables_added: int = 0
    tables_updated: int = 0
    columns_added: int = 0
    columns_updated: int = 0
    fks_synced: int = 0
    indexed_count: int = 0
    orphan_columns: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _pick_description(
    existing: str | None,
    modal_description: str | None,
    remote_comment: str | None,
) -> str | None:
    if existing and existing.strip():
        return existing
    if modal_description and modal_description.strip():
        return modal_description.strip()
    if remote_comment and remote_comment.strip():
        return remote_comment.strip()
    return None


async def _load_existing_tables(
    session: AsyncSession, datasource_id: int
) -> dict[str, TableMetadata]:
    result = await session.execute(
        select(TableMetadata).where(TableMetadata.datasource_id == datasource_id)
    )
    return {t.table_name: t for t in result.scalars().all()}


async def _load_existing_columns(session: AsyncSession, table_id: int) -> dict[str, ColumnMetadata]:
    result = await session.execute(
        select(ColumnMetadata).where(ColumnMetadata.table_id == table_id)
    )
    return {c.column_name: c for c in result.scalars().all()}


async def sync_datasource_metadata(
    session: AsyncSession,
    datasource_id: int,
    connection_url: str,
    items: list[SyncTableItem],
    options: SyncMetadataOptions,
    introspection: IntrospectionResult | None = None,
) -> SyncResult:
    if not items:
        return SyncResult()

    remote = introspection or await introspect_mysql(connection_url)
    remote_by_name = {t.table_name: t for t in remote.tables}
    selected_names = {item.table_name for item in items}
    result = SyncResult()
    existing_tables = await _load_existing_tables(session, datasource_id)
    synced_table_ids: dict[str, int] = {}

    for item in items:
        scanned = remote_by_name.get(item.table_name)
        if not scanned:
            result.errors.append(f"远程库中未找到表: {item.table_name}")
            continue

        existing = existing_tables.get(item.table_name)
        description = _pick_description(
            existing.description if existing else None,
            item.description,
            scanned.table_comment,
        )

        if existing:
            existing.description = description
            existing.is_allowed = item.is_allowed
            table = existing
            result.tables_updated += 1
        else:
            table = TableMetadata(
                datasource_id=datasource_id,
                table_name=item.table_name,
                description=description,
                is_allowed=item.is_allowed,
            )
            session.add(table)
            result.tables_added += 1

        await session.flush()
        synced_table_ids[item.table_name] = table.id

        existing_cols = await _load_existing_columns(session, table.id)
        remote_col_names = {c.column_name for c in scanned.columns}

        for col in scanned.columns:
            existing_col = existing_cols.get(col.column_name)
            col_description = _pick_description(
                existing_col.description if existing_col else None,
                None,
                col.description,
            )
            if existing_col:
                existing_col.data_type = col.data_type
                if col_description is not None:
                    existing_col.description = col_description
                result.columns_updated += 1
            else:
                session.add(
                    ColumnMetadata(
                        table_id=table.id,
                        column_name=col.column_name,
                        data_type=col.data_type,
                        description=col_description,
                    )
                )
                result.columns_added += 1

        for col_name, existing_col in existing_cols.items():
            if col_name not in remote_col_names:
                result.orphan_columns.append(f"{item.table_name}.{col_name}")

    if options.sync_fks and synced_table_ids:
        table_ids = list(synced_table_ids.values())
        await session.execute(
            delete(FkRelationship).where(
                FkRelationship.datasource_id == datasource_id,
                FkRelationship.from_table_id.in_(table_ids),
            )
        )
        await session.flush()

        name_to_id: dict[str, int] = {
            name: tbl.id for name, tbl in existing_tables.items()
        }
        name_to_id.update(synced_table_ids)
        for fk in remote.foreign_keys:
            if fk.from_table not in selected_names:
                continue
            if fk.to_table not in selected_names:
                result.errors.append(
                    f"跳过 FK {fk.from_table}.{fk.from_column} -> "
                    f"{fk.to_table}.{fk.to_column}（目标表未同步）"
                )
                continue
            from_id = name_to_id.get(fk.from_table)
            to_id = name_to_id.get(fk.to_table)
            if not from_id or not to_id:
                continue
            session.add(
                FkRelationship(
                    datasource_id=datasource_id,
                    from_table_id=from_id,
                    from_column=fk.from_column,
                    to_table_id=to_id,
                    to_column=fk.to_column,
                )
            )
            result.fks_synced += 1

    await session.commit()

    if options.index_to_rag:
        pipeline = IndexPipeline(session)
        for table_name in selected_names:
            table_id = synced_table_ids.get(table_name)
            if not table_id:
                continue
            try:
                ok = await pipeline.index_table(table_id)
                if ok:
                    result.indexed_count += 1
                else:
                    result.errors.append(f"RAG 索引失败: {table_name}")
            except Exception as e:
                result.errors.append(f"RAG 索引失败 {table_name}: {e}")
        await session.commit()

    return result


async def scan_datasource_tables(
    session: AsyncSession,
    datasource_id: int,
    connection_url: str,
) -> list[tuple[ScannedTable, bool, int | None]]:
    """Return (scanned_table, already_exists, existing_table_id)."""
    remote = await introspect_mysql(connection_url)
    existing = await _load_existing_tables(session, datasource_id)
    return [
        (
            table,
            table.table_name in existing,
            existing[table.table_name].id if table.table_name in existing else None,
        )
        for table in remote.tables
    ]
