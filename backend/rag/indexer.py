"""RAG document indexing pipeline."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import (
    BusinessGlossary,
    ColumnMetadata,
    FkRelationship,
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
        await self.session.commit()
        return count

    async def _index_tables(self, datasource_id: int) -> int:
        result = await self.session.execute(
            select(TableMetadata, ColumnMetadata)
            .join(ColumnMetadata, ColumnMetadata.table_id == TableMetadata.id)
            .where(TableMetadata.datasource_id == datasource_id)
        )
        table_cols: dict[int, list] = {}
        tables: dict[int, TableMetadata] = {}
        for table, col in result.all():
            tables[table.id] = table
            table_cols.setdefault(table.id, []).append(col)

        count = 0
        for table_id, table in tables.items():
            cols = table_cols.get(table_id, [])
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
                source_id=table_id,
                title=table.table_name,
                content=content,
                datasource_id=datasource_id,
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
                datasource_id=datasource_id,
                metadata={"table_name": table.table_name},
            )
            chunk.qdrant_point_id = point_id
            count += 1
        return count

    async def _index_templates(self, datasource_id: int) -> int:
        result = await self.session.execute(
            select(SqlTemplate).where(SqlTemplate.datasource_id == datasource_id)
        )
        count = 0
        for tpl in result.scalars().all():
            content = f"Question: {tpl.question}\nSQL: {tpl.sql_text}"
            if tpl.description:
                content += f"\nDescription: {tpl.description}"

            doc = RagDocument(
                doc_type="sql_template",
                source_id=tpl.id,
                title=tpl.question[:255],
                content=content,
                datasource_id=datasource_id,
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
                datasource_id=datasource_id,
            )
            chunk.qdrant_point_id = point_id
            count += 1
        return count

    async def _index_glossary(self) -> int:
        result = await self.session.execute(select(BusinessGlossary))
        count = 0
        for term in result.scalars().all():
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
            count += 1
        return count

    async def _index_fk(self, datasource_id: int) -> int:
        result = await self.session.execute(
            select(FkRelationship, TableMetadata)
            .join(TableMetadata, FkRelationship.from_table_id == TableMetadata.id)
            .where(FkRelationship.datasource_id == datasource_id)
        )
        count = 0
        for fk, from_table in result.all():
            to_table = await self.session.get(TableMetadata, fk.to_table_id)
            if not to_table:
                continue
            content = (
                f"FK: {from_table.table_name}.{fk.from_column} -> "
                f"{to_table.table_name}.{fk.to_column}"
            )
            doc = RagDocument(
                doc_type="fk_relationship",
                source_id=fk.id,
                title=f"{from_table.table_name}->{to_table.table_name}",
                content=content,
                datasource_id=datasource_id,
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
                datasource_id=datasource_id,
            )
            chunk.qdrant_point_id = point_id
            count += 1
        return count
