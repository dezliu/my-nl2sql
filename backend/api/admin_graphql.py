"""GraphQL types and resolvers for admin CRUD extensions."""

from typing import Optional

import strawberry
from sqlalchemy import select

from backend.db.models import (
    BusinessGlossary,
    ColumnMetadata,
    FkRelationship,
    KnowledgeEntry,
    SqlTemplate,
    TableMetadata,
    TemplateRecommendation,
)
from backend.db.session import async_session_factory
from backend.rag.index_ops import index_item as do_index_item, unindex_item as do_unindex_item
from backend.rag.retriever import HybridRetriever
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


@strawberry.type
class AdminMutationMixin:
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
