"""GraphQL types and resolvers for admin CRUD extensions."""

from typing import Optional

import strawberry
from sqlalchemy import String, cast, delete, or_, select

from backend.db.models import (
    BusinessGlossary,
    ColumnMetadata,
    Conversation,
    Datasource,
    FkRelationship,
    KnowledgeEntry,
    Message,
    MessageSql,
    RagDocument,
    RagChunk,
    RagEvalCase,
    RagEvalRun,
    RagEvalRunItem,
    SqlTemplate,
    TableMetadata,
    TemplateRecommendation,
)
from backend.db.session import async_session_factory
from backend.db.system_config import get_sql_row_limit, set_sql_row_limit
from backend.eval.rag_eval import DEFAULT_BENCHMARK_PATH, import_cases_from_json, run_rag_eval
from backend.rag.index_ops import index_item as do_index_item, unindex_item as do_unindex_item
from backend.rag.indexer import IndexPipeline
from backend.rag.retriever import HybridRetriever
from backend.services.metadata_sync import (
    SyncMetadataOptions,
    SyncTableItem,
    scan_datasource_tables,
    sync_datasource_metadata,
)
from backend.services.template_recommender import approve_recommendation, reject_recommendation


@strawberry.type
class ColumnMetadataType:
    id: int
    table_id: int
    column_name: str
    data_type: str
    description: Optional[str]
    is_blacklisted: bool


@strawberry.type
class FkRelationshipType:
    id: int
    datasource_id: int
    from_table_id: int
    from_column: str
    to_table_id: int
    to_column: str


@strawberry.type
class BusinessGlossaryType:
    id: int
    term: str
    definition: str
    aliases: Optional[str]
    is_indexed: bool


@strawberry.type
class KnowledgeEntryType:
    id: int
    datasource_id: Optional[int]
    category: str
    title: str
    content: str
    is_indexed: bool


@strawberry.type
class SqlTemplateType:
    id: int
    datasource_id: int
    question: str
    sql_text: str
    description: Optional[str]
    use_count: int
    is_indexed: bool


@strawberry.type
class TemplateRecommendationType:
    id: int
    datasource_id: int
    message_sql_id: int
    question: str
    sql_text: str
    quality_score: float
    status: str


@strawberry.type
class RagSearchResultType:
    chunk_id: str
    content: str
    score: float
    doc_type: str


@strawberry.type
class RagEvalCaseType:
    id: int
    question: str
    datasource_id: Optional[int]
    expected_chunk_ids: Optional[list[int]]
    expected_tables: Optional[list[str]]
    enabled: bool
    note: Optional[str]


@strawberry.type
class RagEvalRunItemType:
    id: int
    case_id: int
    question: str
    recall: float
    mrr: float
    match_mode: str
    retrieved_chunk_ids: list[str]
    hit_chunk_ids: list[str]
    skipped: bool
    skip_reason: Optional[str]


@strawberry.type
class RagEvalRunType:
    id: int
    top_k: int
    datasource_id: Optional[int]
    case_count: int
    recall_at_k: Optional[float]
    mrr: Optional[float]
    status: str
    error_message: Optional[str]
    created_at: str
    items: list[RagEvalRunItemType]


@strawberry.type
class RagEvalSummaryType:
    run_id: int
    case_count: int
    evaluated_count: int
    skipped_count: int
    recall_at_k: float
    mrr: float


@strawberry.type
class RagEvalImportResultType:
    imported_count: int
    skipped_count: int


@strawberry.type
class RagEvalChunkOptionType:
    id: int
    label: str
    doc_type: str
    title: str


@strawberry.type
class ScannedColumnType:
    column_name: str
    data_type: str
    description: Optional[str]
    is_nullable: bool


@strawberry.type
class ScannedTableType:
    table_name: str
    table_comment: Optional[str]
    column_count: int
    already_exists: bool
    existing_table_id: Optional[int]
    columns: list[ScannedColumnType]


@strawberry.type
class SyncResultType:
    tables_added: int
    tables_updated: int
    columns_added: int
    columns_updated: int
    fks_synced: int
    indexed_count: int
    orphan_columns: list[str]
    errors: list[str]


@strawberry.input
class SyncTableItemInput:
    table_name: str
    description: Optional[str] = None
    is_allowed: bool = True


@strawberry.input
class SyncDatasourceMetadataInput:
    datasource_id: int
    tables: list[SyncTableItemInput]
    sync_fks: bool = True
    index_to_rag: bool = False


@strawberry.type
class TableMetadataDetailType:
    id: int
    table_name: str
    description: Optional[str]
    is_allowed: bool
    is_indexed: bool


@strawberry.input
class CreateTableInput:
    datasource_id: int
    table_name: str
    description: Optional[str] = None
    is_allowed: bool = True


@strawberry.input
class UpdateTableInput:
    id: int
    table_name: Optional[str] = None
    description: Optional[str] = None
    is_allowed: Optional[bool] = None


@strawberry.input
class CreateColumnInput:
    table_id: int
    column_name: str
    data_type: str
    description: Optional[str] = None
    is_blacklisted: bool = False


@strawberry.input
class UpdateColumnInput:
    id: int
    column_name: Optional[str] = None
    data_type: Optional[str] = None
    description: Optional[str] = None
    is_blacklisted: Optional[bool] = None


@strawberry.input
class CreateFkInput:
    datasource_id: int
    from_table_id: int
    from_column: str
    to_table_id: int
    to_column: str


@strawberry.input
class CreateGlossaryInput:
    term: str
    definition: str
    aliases: Optional[str] = None


@strawberry.input
class UpdateGlossaryInput:
    id: int
    term: Optional[str] = None
    definition: Optional[str] = None
    aliases: Optional[str] = None


@strawberry.input
class CreateKnowledgeInput:
    title: str
    content: str
    category: str = "faq"
    datasource_id: Optional[int] = None


@strawberry.input
class UpdateKnowledgeInput:
    id: int
    title: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    datasource_id: Optional[int] = None


@strawberry.input
class CreateTemplateInput:
    datasource_id: int
    question: str
    sql_text: str
    description: Optional[str] = None


@strawberry.input
class UpdateTemplateInput:
    id: int
    question: Optional[str] = None
    sql_text: Optional[str] = None
    description: Optional[str] = None


@strawberry.input
class IndexItemInput:
    doc_type: str
    source_id: int


@strawberry.input
class CreateRagEvalCaseInput:
    question: str
    datasource_id: Optional[int] = None
    expected_chunk_ids: Optional[list[int]] = None
    expected_tables: Optional[list[str]] = None
    enabled: bool = True
    note: Optional[str] = None


@strawberry.input
class UpdateRagEvalCaseInput:
    id: int
    question: Optional[str] = None
    datasource_id: Optional[int] = None
    expected_chunk_ids: Optional[list[int]] = None
    expected_tables: Optional[list[str]] = None
    enabled: Optional[bool] = None
    note: Optional[str] = None


def _rag_eval_case_type(case: RagEvalCase) -> RagEvalCaseType:
    chunk_ids = case.expected_chunk_ids
    if chunk_ids is not None:
        chunk_ids = [int(cid) for cid in chunk_ids]
    tables = case.expected_tables
    if tables is not None:
        tables = [str(t) for t in tables]
    return RagEvalCaseType(
        id=case.id,
        question=case.question,
        datasource_id=case.datasource_id,
        expected_chunk_ids=chunk_ids,
        expected_tables=tables,
        enabled=case.enabled,
        note=case.note,
    )


async def _load_rag_eval_run(
    session, run_id: int, *, include_items: bool = True
) -> Optional[RagEvalRunType]:
    run = await session.get(RagEvalRun, run_id)
    if not run:
        return None

    items: list[RagEvalRunItemType] = []
    if include_items:
        items_result = await session.execute(
            select(RagEvalRunItem, RagEvalCase)
            .join(RagEvalCase, RagEvalRunItem.case_id == RagEvalCase.id)
            .where(RagEvalRunItem.run_id == run_id)
            .order_by(RagEvalRunItem.id)
        )
        items = [
            RagEvalRunItemType(
                id=item.id,
                case_id=item.case_id,
                question=case.question,
                recall=item.recall,
                mrr=item.mrr,
                match_mode=item.match_mode,
                retrieved_chunk_ids=[str(cid) for cid in (item.retrieved_chunk_ids or [])],
                hit_chunk_ids=[str(cid) for cid in (item.hit_chunk_ids or [])],
                skipped=item.skipped,
                skip_reason=item.skip_reason,
            )
            for item, case in items_result.all()
        ]
    created = run.created_at.isoformat() if run.created_at else ""
    return RagEvalRunType(
        id=run.id,
        top_k=run.top_k,
        datasource_id=run.datasource_id,
        case_count=run.case_count,
        recall_at_k=run.recall_at_k,
        mrr=run.mrr,
        status=run.status,
        error_message=run.error_message,
        created_at=created,
        items=items,
    )


@strawberry.type
class AdminQueryMixin:
    @strawberry.field
    async def table_detail(self, table_id: int) -> Optional[TableMetadataDetailType]:
        async with async_session_factory() as session:
            table = await session.get(TableMetadata, table_id)
            if not table:
                return None
            return TableMetadataDetailType(
                id=table.id,
                table_name=table.table_name,
                description=table.description,
                is_allowed=table.is_allowed,
                is_indexed=table.is_indexed,
            )

    @strawberry.field
    async def tables_detail(self, datasource_id: int) -> list[TableMetadataDetailType]:
        async with async_session_factory() as session:
            result = await session.execute(
                select(TableMetadata).where(TableMetadata.datasource_id == datasource_id)
            )
            return [
                TableMetadataDetailType(
                    id=t.id,
                    table_name=t.table_name,
                    description=t.description,
                    is_allowed=t.is_allowed,
                    is_indexed=t.is_indexed,
                )
                for t in result.scalars().all()
            ]

    @strawberry.field
    async def columns(self, table_id: int) -> list[ColumnMetadataType]:
        async with async_session_factory() as session:
            result = await session.execute(
                select(ColumnMetadata).where(ColumnMetadata.table_id == table_id)
            )
            return [
                ColumnMetadataType(
                    id=c.id,
                    table_id=c.table_id,
                    column_name=c.column_name,
                    data_type=c.data_type,
                    description=c.description,
                    is_blacklisted=c.is_blacklisted,
                )
                for c in result.scalars().all()
            ]

    @strawberry.field
    async def fk_relationships(self, datasource_id: int) -> list[FkRelationshipType]:
        async with async_session_factory() as session:
            result = await session.execute(
                select(FkRelationship).where(FkRelationship.datasource_id == datasource_id)
            )
            return [
                FkRelationshipType(
                    id=f.id,
                    datasource_id=f.datasource_id,
                    from_table_id=f.from_table_id,
                    from_column=f.from_column,
                    to_table_id=f.to_table_id,
                    to_column=f.to_column,
                )
                for f in result.scalars().all()
            ]

    @strawberry.field
    async def business_glossary(self) -> list[BusinessGlossaryType]:
        async with async_session_factory() as session:
            result = await session.execute(select(BusinessGlossary))
            return [
                BusinessGlossaryType(
                    id=g.id,
                    term=g.term,
                    definition=g.definition,
                    aliases=g.aliases,
                    is_indexed=g.is_indexed,
                )
                for g in result.scalars().all()
            ]

    @strawberry.field
    async def knowledge_entries(
        self, datasource_id: Optional[int] = None
    ) -> list[KnowledgeEntryType]:
        async with async_session_factory() as session:
            q = select(KnowledgeEntry)
            if datasource_id is not None:
                q = q.where(
                    (KnowledgeEntry.datasource_id == datasource_id)
                    | (KnowledgeEntry.datasource_id.is_(None))
                )
            result = await session.execute(q)
            return [
                KnowledgeEntryType(
                    id=e.id,
                    datasource_id=e.datasource_id,
                    category=e.category,
                    title=e.title,
                    content=e.content,
                    is_indexed=e.is_indexed,
                )
                for e in result.scalars().all()
            ]

    @strawberry.field
    async def sql_templates(self, datasource_id: int) -> list[SqlTemplateType]:
        async with async_session_factory() as session:
            result = await session.execute(
                select(SqlTemplate).where(SqlTemplate.datasource_id == datasource_id)
            )
            return [
                SqlTemplateType(
                    id=t.id,
                    datasource_id=t.datasource_id,
                    question=t.question,
                    sql_text=t.sql_text,
                    description=t.description,
                    use_count=t.use_count,
                    is_indexed=t.is_indexed,
                )
                for t in result.scalars().all()
            ]

    @strawberry.field
    async def template_recommendations(
        self, status: Optional[str] = "pending"
    ) -> list[TemplateRecommendationType]:
        async with async_session_factory() as session:
            q = select(TemplateRecommendation)
            if status:
                q = q.where(TemplateRecommendation.status == status)
            result = await session.execute(q.order_by(TemplateRecommendation.created_at.desc()))
            return [
                TemplateRecommendationType(
                    id=r.id,
                    datasource_id=r.datasource_id,
                    message_sql_id=r.message_sql_id,
                    question=r.question,
                    sql_text=r.sql_text,
                    quality_score=r.quality_score,
                    status=r.status,
                )
                for r in result.scalars().all()
            ]

    @strawberry.field
    async def test_rag_search(
        self, query: str, datasource_id: Optional[int] = None, top_k: int = 5
    ) -> list[RagSearchResultType]:
        retriever = HybridRetriever()
        results = retriever.search(query, top_k=top_k, datasource_id=datasource_id)
        return [
            RagSearchResultType(
                chunk_id=r.chunk_id,
                content=r.content,
                score=r.score,
                doc_type=r.doc_type,
            )
            for r in results
        ]

    @strawberry.field
    async def rag_eval_cases(self, enabled: Optional[bool] = None) -> list[RagEvalCaseType]:
        async with async_session_factory() as session:
            q = select(RagEvalCase).order_by(RagEvalCase.id)
            if enabled is not None:
                q = q.where(RagEvalCase.enabled == enabled)
            result = await session.execute(q)
            return [_rag_eval_case_type(c) for c in result.scalars().all()]

    @strawberry.field
    async def rag_eval_runs(self, limit: int = 20) -> list[RagEvalRunType]:
        async with async_session_factory() as session:
            result = await session.execute(
                select(RagEvalRun).order_by(RagEvalRun.id.desc()).limit(limit)
            )
            runs = []
            for run in result.scalars().all():
                loaded = await _load_rag_eval_run(session, run.id, include_items=False)
                if loaded:
                    runs.append(loaded)
            return runs

    @strawberry.field
    async def rag_eval_run(self, run_id: int) -> Optional[RagEvalRunType]:
        async with async_session_factory() as session:
            return await _load_rag_eval_run(session, run_id)

    @strawberry.field
    async def rag_eval_chunks(
        self,
        datasource_id: Optional[int] = None,
        search: Optional[str] = None,
        limit: int = 200,
    ) -> list[RagEvalChunkOptionType]:
        async with async_session_factory() as session:
            q = (
                select(RagChunk, RagDocument)
                .join(RagDocument, RagChunk.document_id == RagDocument.id)
                .order_by(RagChunk.id.desc())
                .limit(min(limit, 500))
            )
            if datasource_id is not None:
                q = q.where(RagDocument.datasource_id == datasource_id)
            if search and search.strip():
                term = f"%{search.strip()}%"
                q = q.where(
                    or_(
                        RagDocument.title.like(term),
                        RagChunk.content.like(term),
                        RagDocument.doc_type.like(term),
                        cast(RagChunk.id, String).like(term),
                    )
                )
            result = await session.execute(q)
            return [
                RagEvalChunkOptionType(
                    id=chunk.id,
                    label=f"#{chunk.id} · {doc.doc_type} · {doc.title[:48]}",
                    doc_type=doc.doc_type,
                    title=doc.title,
                )
                for chunk, doc in result.all()
            ]

    @strawberry.field
    async def scan_datasource_tables(self, datasource_id: int) -> list[ScannedTableType]:
        async with async_session_factory() as session:
            ds = await session.get(Datasource, datasource_id)
            if not ds:
                return []
            rows = await scan_datasource_tables(session, datasource_id, ds.connection_url)
            return [
                ScannedTableType(
                    table_name=table.table_name,
                    table_comment=table.table_comment,
                    column_count=len(table.columns),
                    already_exists=exists,
                    existing_table_id=existing_id,
                    columns=[
                        ScannedColumnType(
                            column_name=c.column_name,
                            data_type=c.data_type,
                            description=c.description,
                            is_nullable=c.is_nullable,
                        )
                        for c in table.columns
                    ],
                )
                for table, exists, existing_id in rows
            ]


    @strawberry.field
    async def sql_row_limit(self) -> int:
        async with async_session_factory() as session:
            return await get_sql_row_limit(session)


async def _purge_datasource_rag(
    session, pipeline: IndexPipeline, datasource_id: int
) -> None:
    result = await session.execute(
        select(RagDocument).where(RagDocument.datasource_id == datasource_id)
    )
    for doc in result.scalars().all():
        if doc.source_id:
            await pipeline.unindex_by_source(doc.doc_type, doc.source_id)


async def delete_datasource_cascade(session, datasource_id: int) -> bool:
    ds = await session.get(Datasource, datasource_id)
    if not ds:
        return False

    pipeline = IndexPipeline(session)
    await _purge_datasource_rag(session, pipeline, datasource_id)

    await session.execute(
        delete(TemplateRecommendation).where(
            TemplateRecommendation.datasource_id == datasource_id
        )
    )

    conv_result = await session.execute(
        select(Conversation).where(Conversation.datasource_id == datasource_id)
    )
    for conv in conv_result.scalars().all():
        msg_result = await session.execute(
            select(Message).where(Message.conversation_id == conv.id)
        )
        for msg in msg_result.scalars().all():
            await session.execute(delete(MessageSql).where(MessageSql.message_id == msg.id))
            await session.delete(msg)
        await session.delete(conv)

    await session.execute(
        delete(FkRelationship).where(FkRelationship.datasource_id == datasource_id)
    )

    table_result = await session.execute(
        select(TableMetadata).where(TableMetadata.datasource_id == datasource_id)
    )
    for table in table_result.scalars().all():
        await session.execute(delete(ColumnMetadata).where(ColumnMetadata.table_id == table.id))
        await session.delete(table)

    await session.execute(delete(SqlTemplate).where(SqlTemplate.datasource_id == datasource_id))
    await session.execute(
        delete(KnowledgeEntry).where(KnowledgeEntry.datasource_id == datasource_id)
    )

    await session.delete(ds)
    return True


@strawberry.type
class AdminMutationMixin:
    @strawberry.mutation
    async def update_sql_row_limit(self, limit: int) -> int:
        async with async_session_factory() as session:
            try:
                await set_sql_row_limit(session, limit)
            except ValueError as e:
                raise ValueError(str(e)) from e
            return limit

    @strawberry.mutation
    async def sync_datasource_metadata(
        self, input: SyncDatasourceMetadataInput
    ) -> SyncResultType:
        async with async_session_factory() as session:
            ds = await session.get(Datasource, input.datasource_id)
            if not ds:
                return SyncResultType(
                    tables_added=0,
                    tables_updated=0,
                    columns_added=0,
                    columns_updated=0,
                    fks_synced=0,
                    indexed_count=0,
                    orphan_columns=[],
                    errors=["数据源不存在"],
                )
            items = [
                SyncTableItem(
                    table_name=t.table_name,
                    description=t.description,
                    is_allowed=t.is_allowed,
                )
                for t in input.tables
            ]
            options = SyncMetadataOptions(
                sync_fks=input.sync_fks,
                index_to_rag=input.index_to_rag,
            )
            try:
                result = await sync_datasource_metadata(
                    session,
                    input.datasource_id,
                    ds.connection_url,
                    items,
                    options,
                )
            except ValueError as e:
                return SyncResultType(
                    tables_added=0,
                    tables_updated=0,
                    columns_added=0,
                    columns_updated=0,
                    fks_synced=0,
                    indexed_count=0,
                    orphan_columns=[],
                    errors=[str(e)],
                )
            return SyncResultType(
                tables_added=result.tables_added,
                tables_updated=result.tables_updated,
                columns_added=result.columns_added,
                columns_updated=result.columns_updated,
                fks_synced=result.fks_synced,
                indexed_count=result.indexed_count,
                orphan_columns=result.orphan_columns,
                errors=result.errors,
            )

    @strawberry.mutation
    async def create_table(self, input: CreateTableInput) -> TableMetadataDetailType:
        async with async_session_factory() as session:
            table = TableMetadata(
                datasource_id=input.datasource_id,
                table_name=input.table_name,
                description=input.description,
                is_allowed=input.is_allowed,
            )
            session.add(table)
            await session.commit()
            await session.refresh(table)
            return TableMetadataDetailType(
                id=table.id,
                table_name=table.table_name,
                description=table.description,
                is_allowed=table.is_allowed,
                is_indexed=table.is_indexed,
            )

    @strawberry.mutation
    async def update_table(self, input: UpdateTableInput) -> Optional[TableMetadataDetailType]:
        async with async_session_factory() as session:
            table = await session.get(TableMetadata, input.id)
            if not table:
                return None
            if input.table_name is not None:
                table.table_name = input.table_name
            if input.description is not None:
                table.description = input.description
            if input.is_allowed is not None:
                table.is_allowed = input.is_allowed
            await session.commit()
            await session.refresh(table)
            return TableMetadataDetailType(
                id=table.id,
                table_name=table.table_name,
                description=table.description,
                is_allowed=table.is_allowed,
                is_indexed=table.is_indexed,
            )

    @strawberry.mutation
    async def delete_table(self, table_id: int) -> bool:
        async with async_session_factory() as session:
            table = await session.get(TableMetadata, table_id)
            if not table:
                return False
            await do_unindex_item(session, "table_metadata", table_id)
            await session.delete(table)
            await session.commit()
            return True

    @strawberry.mutation
    async def create_column(self, input: CreateColumnInput) -> ColumnMetadataType:
        async with async_session_factory() as session:
            col = ColumnMetadata(
                table_id=input.table_id,
                column_name=input.column_name,
                data_type=input.data_type,
                description=input.description,
                is_blacklisted=input.is_blacklisted,
            )
            session.add(col)
            await session.commit()
            await session.refresh(col)
            return ColumnMetadataType(
                id=col.id,
                table_id=col.table_id,
                column_name=col.column_name,
                data_type=col.data_type,
                description=col.description,
                is_blacklisted=col.is_blacklisted,
            )

    @strawberry.mutation
    async def update_column(self, input: UpdateColumnInput) -> Optional[ColumnMetadataType]:
        async with async_session_factory() as session:
            col = await session.get(ColumnMetadata, input.id)
            if not col:
                return None
            if input.column_name is not None:
                col.column_name = input.column_name
            if input.data_type is not None:
                col.data_type = input.data_type
            if input.description is not None:
                col.description = input.description
            if input.is_blacklisted is not None:
                col.is_blacklisted = input.is_blacklisted
            await session.commit()
            await session.refresh(col)
            return ColumnMetadataType(
                id=col.id,
                table_id=col.table_id,
                column_name=col.column_name,
                data_type=col.data_type,
                description=col.description,
                is_blacklisted=col.is_blacklisted,
            )

    @strawberry.mutation
    async def delete_column(self, column_id: int) -> bool:
        async with async_session_factory() as session:
            col = await session.get(ColumnMetadata, column_id)
            if not col:
                return False
            await session.delete(col)
            await session.commit()
            return True

    @strawberry.mutation
    async def create_fk(self, input: CreateFkInput) -> FkRelationshipType:
        async with async_session_factory() as session:
            fk = FkRelationship(
                datasource_id=input.datasource_id,
                from_table_id=input.from_table_id,
                from_column=input.from_column,
                to_table_id=input.to_table_id,
                to_column=input.to_column,
            )
            session.add(fk)
            await session.commit()
            await session.refresh(fk)
            return FkRelationshipType(
                id=fk.id,
                datasource_id=fk.datasource_id,
                from_table_id=fk.from_table_id,
                from_column=fk.from_column,
                to_table_id=fk.to_table_id,
                to_column=fk.to_column,
            )

    @strawberry.mutation
    async def delete_fk(self, fk_id: int) -> bool:
        async with async_session_factory() as session:
            fk = await session.get(FkRelationship, fk_id)
            if not fk:
                return False
            await do_unindex_item(session, "fk_relationship", fk_id)
            await session.delete(fk)
            await session.commit()
            return True

    @strawberry.mutation
    async def create_glossary(self, input: CreateGlossaryInput) -> BusinessGlossaryType:
        async with async_session_factory() as session:
            term = BusinessGlossary(
                term=input.term,
                definition=input.definition,
                aliases=input.aliases,
            )
            session.add(term)
            await session.commit()
            await session.refresh(term)
            return BusinessGlossaryType(
                id=term.id,
                term=term.term,
                definition=term.definition,
                aliases=term.aliases,
                is_indexed=term.is_indexed,
            )

    @strawberry.mutation
    async def update_glossary(self, input: UpdateGlossaryInput) -> Optional[BusinessGlossaryType]:
        async with async_session_factory() as session:
            term = await session.get(BusinessGlossary, input.id)
            if not term:
                return None
            if input.term is not None:
                term.term = input.term
            if input.definition is not None:
                term.definition = input.definition
            if input.aliases is not None:
                term.aliases = input.aliases
            await session.commit()
            await session.refresh(term)
            return BusinessGlossaryType(
                id=term.id,
                term=term.term,
                definition=term.definition,
                aliases=term.aliases,
                is_indexed=term.is_indexed,
            )

    @strawberry.mutation
    async def delete_glossary(self, glossary_id: int) -> bool:
        async with async_session_factory() as session:
            term = await session.get(BusinessGlossary, glossary_id)
            if not term:
                return False
            await do_unindex_item(session, "glossary", glossary_id)
            await session.delete(term)
            await session.commit()
            return True

    @strawberry.mutation
    async def create_knowledge(self, input: CreateKnowledgeInput) -> KnowledgeEntryType:
        async with async_session_factory() as session:
            entry = KnowledgeEntry(
                title=input.title,
                content=input.content,
                category=input.category,
                datasource_id=input.datasource_id,
            )
            session.add(entry)
            await session.commit()
            await session.refresh(entry)
            return KnowledgeEntryType(
                id=entry.id,
                datasource_id=entry.datasource_id,
                category=entry.category,
                title=entry.title,
                content=entry.content,
                is_indexed=entry.is_indexed,
            )

    @strawberry.mutation
    async def update_knowledge(self, input: UpdateKnowledgeInput) -> Optional[KnowledgeEntryType]:
        async with async_session_factory() as session:
            entry = await session.get(KnowledgeEntry, input.id)
            if not entry:
                return None
            if input.title is not None:
                entry.title = input.title
            if input.content is not None:
                entry.content = input.content
            if input.category is not None:
                entry.category = input.category
            if input.datasource_id is not None:
                entry.datasource_id = input.datasource_id
            await session.commit()
            await session.refresh(entry)
            return KnowledgeEntryType(
                id=entry.id,
                datasource_id=entry.datasource_id,
                category=entry.category,
                title=entry.title,
                content=entry.content,
                is_indexed=entry.is_indexed,
            )

    @strawberry.mutation
    async def delete_knowledge(self, entry_id: int) -> bool:
        async with async_session_factory() as session:
            entry = await session.get(KnowledgeEntry, entry_id)
            if not entry:
                return False
            await do_unindex_item(session, "knowledge", entry_id)
            await session.delete(entry)
            await session.commit()
            return True

    @strawberry.mutation
    async def create_template(self, input: CreateTemplateInput) -> SqlTemplateType:
        async with async_session_factory() as session:
            tpl = SqlTemplate(
                datasource_id=input.datasource_id,
                question=input.question,
                sql_text=input.sql_text,
                description=input.description,
            )
            session.add(tpl)
            await session.commit()
            await session.refresh(tpl)
            return SqlTemplateType(
                id=tpl.id,
                datasource_id=tpl.datasource_id,
                question=tpl.question,
                sql_text=tpl.sql_text,
                description=tpl.description,
                use_count=tpl.use_count,
                is_indexed=tpl.is_indexed,
            )

    @strawberry.mutation
    async def update_template(self, input: UpdateTemplateInput) -> Optional[SqlTemplateType]:
        async with async_session_factory() as session:
            tpl = await session.get(SqlTemplate, input.id)
            if not tpl:
                return None
            if input.question is not None:
                tpl.question = input.question
            if input.sql_text is not None:
                tpl.sql_text = input.sql_text
            if input.description is not None:
                tpl.description = input.description
            await session.commit()
            await session.refresh(tpl)
            return SqlTemplateType(
                id=tpl.id,
                datasource_id=tpl.datasource_id,
                question=tpl.question,
                sql_text=tpl.sql_text,
                description=tpl.description,
                use_count=tpl.use_count,
                is_indexed=tpl.is_indexed,
            )

    @strawberry.mutation
    async def delete_template(self, template_id: int) -> bool:
        async with async_session_factory() as session:
            tpl = await session.get(SqlTemplate, template_id)
            if not tpl:
                return False
            await do_unindex_item(session, "sql_template", template_id)
            await session.delete(tpl)
            await session.commit()
            return True

    @strawberry.mutation
    async def approve_template_recommendation(self, rec_id: int) -> Optional[SqlTemplateType]:
        async with async_session_factory() as session:
            tpl = await approve_recommendation(session, rec_id)
            if not tpl:
                return None
            return SqlTemplateType(
                id=tpl.id,
                datasource_id=tpl.datasource_id,
                question=tpl.question,
                sql_text=tpl.sql_text,
                description=tpl.description,
                use_count=tpl.use_count,
                is_indexed=tpl.is_indexed,
            )

    @strawberry.mutation
    async def reject_template_recommendation(self, rec_id: int) -> bool:
        async with async_session_factory() as session:
            return await reject_recommendation(session, rec_id)

    @strawberry.mutation
    async def index_item(self, input: IndexItemInput) -> bool:
        async with async_session_factory() as session:
            return await do_index_item(session, input.doc_type, input.source_id)

    @strawberry.mutation
    async def unindex_item(self, input: IndexItemInput) -> bool:
        async with async_session_factory() as session:
            return await do_unindex_item(session, input.doc_type, input.source_id)

    @strawberry.mutation
    async def create_rag_eval_case(self, input: CreateRagEvalCaseInput) -> RagEvalCaseType:
        async with async_session_factory() as session:
            case = RagEvalCase(
                question=input.question,
                datasource_id=input.datasource_id,
                expected_chunk_ids=input.expected_chunk_ids,
                expected_tables=input.expected_tables,
                enabled=input.enabled,
                note=input.note,
            )
            session.add(case)
            await session.commit()
            await session.refresh(case)
            return _rag_eval_case_type(case)

    @strawberry.mutation
    async def update_rag_eval_case(self, input: UpdateRagEvalCaseInput) -> Optional[RagEvalCaseType]:
        async with async_session_factory() as session:
            case = await session.get(RagEvalCase, input.id)
            if not case:
                return None
            if input.question is not None:
                case.question = input.question
            if input.datasource_id is not None:
                case.datasource_id = input.datasource_id
            if input.expected_chunk_ids is not None:
                case.expected_chunk_ids = input.expected_chunk_ids
            if input.expected_tables is not None:
                case.expected_tables = input.expected_tables
            if input.enabled is not None:
                case.enabled = input.enabled
            if input.note is not None:
                case.note = input.note
            await session.commit()
            await session.refresh(case)
            return _rag_eval_case_type(case)

    @strawberry.mutation
    async def delete_rag_eval_case(self, case_id: int) -> bool:
        async with async_session_factory() as session:
            case = await session.get(RagEvalCase, case_id)
            if not case:
                return False
            await session.delete(case)
            await session.commit()
            return True

    @strawberry.mutation
    async def import_rag_eval_benchmark(self) -> RagEvalImportResultType:
        async with async_session_factory() as session:
            imported, skipped = await import_cases_from_json(session, DEFAULT_BENCHMARK_PATH)
            return RagEvalImportResultType(imported_count=imported, skipped_count=skipped)

    @strawberry.mutation
    async def run_rag_eval(
        self,
        top_k: int,
        datasource_id: Optional[int] = None,
        case_ids: Optional[list[int]] = None,
    ) -> RagEvalSummaryType:
        async with async_session_factory() as session:
            summary = await run_rag_eval(
                session,
                top_k=top_k,
                datasource_id=datasource_id,
                case_ids=case_ids,
            )
            return RagEvalSummaryType(
                run_id=summary.run_id,
                case_count=summary.case_count,
                evaluated_count=summary.evaluated_count,
                skipped_count=summary.skipped_count,
                recall_at_k=summary.recall_at_k,
                mrr=summary.mrr,
            )
