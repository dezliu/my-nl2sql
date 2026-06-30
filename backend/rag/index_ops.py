"""Single-item RAG indexing and unindexing."""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import (
    BusinessGlossary,
    ColumnMetadata,
    FkRelationship,
    KnowledgeEntry,
    RagChunk,
    RagDocument,
    SqlTemplate,
    TableMetadata,
)
from backend.rag.indexer import IndexPipeline


DOC_TYPE_MAP = {
    "table_metadata": ("table_metadata", TableMetadata),
    "sql_template": ("sql_template", SqlTemplate),
    "glossary": ("glossary", BusinessGlossary),
    "fk_relationship": ("fk_relationship", FkRelationship),
    "knowledge": ("knowledge", KnowledgeEntry),
}


async def index_item(session: AsyncSession, doc_type: str, source_id: int) -> bool:
    if doc_type not in DOC_TYPE_MAP:
        return False
    pipeline = IndexPipeline(session)
    if doc_type == "table_metadata":
        ok = await pipeline.index_table(source_id)
    elif doc_type == "sql_template":
        ok = await pipeline.index_template(source_id)
    elif doc_type == "glossary":
        ok = await pipeline.index_glossary_term(source_id)
    elif doc_type == "fk_relationship":
        ok = await pipeline.index_fk(source_id)
    elif doc_type == "knowledge":
        ok = await pipeline.index_knowledge(source_id)
    else:
        return False
    if ok:
        await _set_indexed_flag(session, doc_type, source_id, True)
        await session.commit()
    return ok


async def unindex_item(session: AsyncSession, doc_type: str, source_id: int) -> bool:
    if doc_type not in DOC_TYPE_MAP:
        return False
    pipeline = IndexPipeline(session)
    removed = await pipeline.unindex_by_source(doc_type, source_id)
    if removed:
        await _set_indexed_flag(session, doc_type, source_id, False)
        await session.commit()
    return removed


async def _set_indexed_flag(
    session: AsyncSession, doc_type: str, source_id: int, value: bool
) -> None:
    mapping = DOC_TYPE_MAP.get(doc_type)
    if not mapping:
        return
    _, model = mapping
    obj = await session.get(model, source_id)
    if obj and hasattr(obj, "is_indexed"):
        obj.is_indexed = value
