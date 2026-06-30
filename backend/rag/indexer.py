"""RAG document indexing pipeline."""

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
from backend.rag.retriever import HybridRetriever


class IndexPipeline:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.retriever = HybridRetriever()

    async def index_all_for_datasource(self, datasource_id: int) -> int:
        count = 0
        count += await self._index_tables(datasource_id)
        count += await self._index_templates(datasource_id)
        count += await self._index_glossary()
        count += await self._index_fk(datasource_id)
        count += await self._index_knowledge_for_datasource(datasource_id)
        await self.session.commit()
        return count

    async def index_table(self, table_id: int) -> bool:
        table = await self.session.get(TableMetadata, table_id)
        if not table:
            return False
        result = await self.session.execute(
            select(ColumnMetadata).where(ColumnMetadata.table_id == table_id)
        )
        cols = list(result.scalars().all())
        await self._store_table_doc(table, cols)
        table.is_indexed = True
        await self.session.flush()
        return True

    async def index_template(self, template_id: int) -> bool:
        tpl = await self.session.get(SqlTemplate, template_id)
        if not tpl:
            return False
        await self._store_template_doc(tpl)
        tpl.is_indexed = True
        await self.session.flush()
        return True

    async def index_glossary_term(self, term_id: int) -> bool:
        term = await self.session.get(BusinessGlossary, term_id)
        if not term:
            return False
        await self._store_glossary_doc(term)
        term.is_indexed = True
        await self.session.flush()
        return True

    async def index_fk(self, fk_id: int) -> bool:
        fk = await self.session.get(FkRelationship, fk_id)
        if not fk:
            return False
        from_table = await self.session.get(TableMetadata, fk.from_table_id)
        to_table = await self.session.get(TableMetadata, fk.to_table_id)
        if not from_table or not to_table:
            return False
        await self._store_fk_doc(fk, from_table, to_table)
        return True

    async def index_knowledge(self, entry_id: int) -> bool:
        entry = await self.session.get(KnowledgeEntry, entry_id)
        if not entry:
            return False
        await self._store_knowledge_doc(entry)
        entry.is_indexed = True
        await self.session.flush()
        return True

    async def unindex_by_source(self, doc_type: str, source_id: int) -> bool:
        result = await self.session.execute(
            select(RagDocument).where(
                RagDocument.doc_type == doc_type, RagDocument.source_id == source_id
            )
        )
        docs = list(result.scalars().all())
        if not docs:
            return False

        for doc in docs:
            chunk_result = await self.session.execute(
                select(RagChunk).where(RagChunk.document_id == doc.id)
            )
            for chunk in chunk_result.scalars().all():
                if chunk.qdrant_point_id:
                    self.retriever.delete_by_chunk_id(chunk.id)
            await self.session.execute(delete(RagChunk).where(RagChunk.document_id == doc.id))
            await self.session.delete(doc)

        await self.session.flush()
        return True

    async def _index_tables(self, datasource_id: int) -> int:
        result = await self.session.execute(
            select(TableMetadata).where(TableMetadata.datasource_id == datasource_id)
        )
        count = 0
        for table in result.scalars().all():
            cols_result = await self.session.execute(
                select(ColumnMetadata).where(ColumnMetadata.table_id == table.id)
            )
            await self._store_table_doc(table, list(cols_result.scalars().all()))
            table.is_indexed = True
            count += 1
        return count

    async def _store_table_doc(self, table: TableMetadata, cols: list[ColumnMetadata]) -> None:
        await self.unindex_by_source("table_metadata", table.id)
        content = f"Table: {table.table_name}\n"
        if table.description:
            content += f"Description: {table.description}\n"
        content += "Columns:\n"
        for c in cols:
            content += f"  - {c.column_name} ({c.data_type})"
            if c.description:
                content += f": {c.description}"
            content += "\n"

        doc = RagDocument(
            doc_type="table_metadata",
            source_id=table.id,
            title=table.table_name,
            content=content,
            datasource_id=table.datasource_id,
        )
        self.session.add(doc)
        await self.session.flush()

        chunk = RagChunk(document_id=doc.id, chunk_index=0, content=content)
        self.session.add(chunk)
        await self.session.flush()

        point_id = self.retriever.index_document(
            content=content,
            doc_type="table_metadata",
            chunk_id=chunk.id,
            datasource_id=table.datasource_id,
            metadata={"table_name": table.table_name},
        )
        chunk.qdrant_point_id = point_id

    async def _index_templates(self, datasource_id: int) -> int:
        result = await self.session.execute(
            select(SqlTemplate).where(SqlTemplate.datasource_id == datasource_id)
        )
        count = 0
        for tpl in result.scalars().all():
            await self._store_template_doc(tpl)
            tpl.is_indexed = True
            count += 1
        return count

    async def _store_template_doc(self, tpl: SqlTemplate) -> None:
        await self.unindex_by_source("sql_template", tpl.id)
        content = f"Question: {tpl.question}\nSQL: {tpl.sql_text}"
        if tpl.description:
            content += f"\nDescription: {tpl.description}"

        doc = RagDocument(
            doc_type="sql_template",
            source_id=tpl.id,
            title=tpl.question[:255],
            content=content,
            datasource_id=tpl.datasource_id,
        )
        self.session.add(doc)
        await self.session.flush()

        chunk = RagChunk(document_id=doc.id, chunk_index=0, content=content)
        self.session.add(chunk)
        await self.session.flush()

        point_id = self.retriever.index_document(
            content=content,
            doc_type="sql_template",
            chunk_id=chunk.id,
            datasource_id=tpl.datasource_id,
        )
        chunk.qdrant_point_id = point_id

    async def _index_glossary(self) -> int:
        result = await self.session.execute(select(BusinessGlossary))
        count = 0
        for term in result.scalars().all():
            await self._store_glossary_doc(term)
            term.is_indexed = True
            count += 1
        return count

    async def _store_glossary_doc(self, term: BusinessGlossary) -> None:
        await self.unindex_by_source("glossary", term.id)
        content = f"Term: {term.term}\nDefinition: {term.definition}"
        if term.aliases:
            content += f"\nAliases: {term.aliases}"

        doc = RagDocument(
            doc_type="glossary",
            source_id=term.id,
            title=term.term,
            content=content,
        )
        self.session.add(doc)
        await self.session.flush()

        chunk = RagChunk(document_id=doc.id, chunk_index=0, content=content)
        self.session.add(chunk)
        await self.session.flush()

        point_id = self.retriever.index_document(
            content=content, doc_type="glossary", chunk_id=chunk.id
        )
        chunk.qdrant_point_id = point_id

    async def _index_fk(self, datasource_id: int) -> int:
        result = await self.session.execute(
            select(FkRelationship).where(FkRelationship.datasource_id == datasource_id)
        )
        count = 0
        for fk in result.scalars().all():
            from_table = await self.session.get(TableMetadata, fk.from_table_id)
            to_table = await self.session.get(TableMetadata, fk.to_table_id)
            if from_table and to_table:
                await self._store_fk_doc(fk, from_table, to_table)
                count += 1
        return count

    async def _store_fk_doc(
        self, fk: FkRelationship, from_table: TableMetadata, to_table: TableMetadata
    ) -> None:
        await self.unindex_by_source("fk_relationship", fk.id)
        content = (
            f"FK: {from_table.table_name}.{fk.from_column} -> "
            f"{to_table.table_name}.{fk.to_column}"
        )
        doc = RagDocument(
            doc_type="fk_relationship",
            source_id=fk.id,
            title=f"{from_table.table_name}->{to_table.table_name}",
            content=content,
            datasource_id=fk.datasource_id,
        )
        self.session.add(doc)
        await self.session.flush()

        chunk = RagChunk(document_id=doc.id, chunk_index=0, content=content)
        self.session.add(chunk)
        await self.session.flush()

        point_id = self.retriever.index_document(
            content=content,
            doc_type="fk_relationship",
            chunk_id=chunk.id,
            datasource_id=fk.datasource_id,
        )
        chunk.qdrant_point_id = point_id

    async def _index_knowledge_for_datasource(self, datasource_id: int) -> int:
        result = await self.session.execute(
            select(KnowledgeEntry).where(
                (KnowledgeEntry.datasource_id == datasource_id)
                | (KnowledgeEntry.datasource_id.is_(None))
            )
        )
        count = 0
        for entry in result.scalars().all():
            await self._store_knowledge_doc(entry)
            entry.is_indexed = True
            count += 1
        return count

    async def _store_knowledge_doc(self, entry: KnowledgeEntry) -> None:
        await self.unindex_by_source("knowledge", entry.id)
        content = f"Category: {entry.category}\nTitle: {entry.title}\n{entry.content}"
        doc = RagDocument(
            doc_type="knowledge",
            source_id=entry.id,
            title=entry.title,
            content=content,
            datasource_id=entry.datasource_id,
        )
        self.session.add(doc)
        await self.session.flush()

        chunk = RagChunk(document_id=doc.id, chunk_index=0, content=content)
        self.session.add(chunk)
        await self.session.flush()

        point_id = self.retriever.index_document(
            content=content,
            doc_type="knowledge",
            chunk_id=chunk.id,
            datasource_id=entry.datasource_id,
            metadata={"category": entry.category},
        )
        chunk.qdrant_point_id = point_id
