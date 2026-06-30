"""SQLAlchemy ORM models for NL2SQL system."""

from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.session import Base


class ExecutionMode(str, PyEnum):
    AUTO = "AUTO"
    GENERATE_ONLY = "GENERATE_ONLY"
    EXECUTE = "EXECUTE"


class PromptRole(str, PyEnum):
    INTENT_CLASSIFIER = "intent_classifier"
    RAG_ROUTER = "rag_router"
    QUERY_EXPANDER = "query_expander"
    RETRIEVAL_JUDGE = "retrieval_judge"
    SQL_GENERATOR = "sql_generator"
    REACT_REASONER = "react_reasoner"
    SQL_SAFETY = "sql_safety"
    RESULT_SUMMARIZER = "result_summarizer"
    RAG_SCORER = "rag_scorer"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    roles: Mapped[list["UserRole"]] = relationship(back_populates="user")


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255))

    permissions: Mapped[list["RolePermission"]] = relationship(back_populates="role")
    users: Mapped[list["UserRole"]] = relationship(back_populates="role")


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255))


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(ForeignKey("permissions.id"), primary_key=True)

    role: Mapped["Role"] = relationship(back_populates="permissions")
    permission: Mapped["Permission"] = relationship()


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), primary_key=True)

    user: Mapped["User"] = relationship(back_populates="roles")
    role: Mapped["Role"] = relationship(back_populates="users")


class Datasource(Base):
    __tablename__ = "datasources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    connection_url: Mapped[str] = mapped_column(String(512), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    tables: Mapped[list["TableMetadata"]] = relationship(back_populates="datasource")


class TableMetadata(Base):
    __tablename__ = "table_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    datasource_id: Mapped[int] = mapped_column(ForeignKey("datasources.id"), nullable=False)
    table_name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    is_indexed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    datasource: Mapped["Datasource"] = relationship(back_populates="tables")
    columns: Mapped[list["ColumnMetadata"]] = relationship(back_populates="table")
    fk_from: Mapped[list["FkRelationship"]] = relationship(
        back_populates="from_table", foreign_keys="FkRelationship.from_table_id"
    )

    __table_args__ = (UniqueConstraint("datasource_id", "table_name"),)


class ColumnMetadata(Base):
    __tablename__ = "column_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("table_metadata.id"), nullable=False)
    column_name: Mapped[str] = mapped_column(String(128), nullable=False)
    data_type: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_blacklisted: Mapped[bool] = mapped_column(Boolean, default=False)

    table: Mapped["TableMetadata"] = relationship(back_populates="columns")

    __table_args__ = (UniqueConstraint("table_id", "column_name"),)


class FkRelationship(Base):
    __tablename__ = "fk_relationships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    datasource_id: Mapped[int] = mapped_column(ForeignKey("datasources.id"), nullable=False)
    from_table_id: Mapped[int] = mapped_column(ForeignKey("table_metadata.id"), nullable=False)
    from_column: Mapped[str] = mapped_column(String(128), nullable=False)
    to_table_id: Mapped[int] = mapped_column(ForeignKey("table_metadata.id"), nullable=False)
    to_column: Mapped[str] = mapped_column(String(128), nullable=False)

    from_table: Mapped["TableMetadata"] = relationship(
        back_populates="fk_from", foreign_keys=[from_table_id]
    )
    to_table: Mapped["TableMetadata"] = relationship(foreign_keys=[to_table_id])


class BusinessGlossary(Base):
    __tablename__ = "business_glossary"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    term: Mapped[str] = mapped_column(String(128), nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    aliases: Mapped[Optional[str]] = mapped_column(Text)
    is_indexed: Mapped[bool] = mapped_column(Boolean, default=False)


class KnowledgeEntry(Base):
    __tablename__ = "knowledge_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    datasource_id: Mapped[Optional[int]] = mapped_column(ForeignKey("datasources.id"))
    category: Mapped[str] = mapped_column(String(64), default="faq")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_indexed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SqlTemplate(Base):
    __tablename__ = "sql_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    datasource_id: Mapped[int] = mapped_column(ForeignKey("datasources.id"), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    sql_text: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    is_indexed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TemplateRecommendation(Base):
    __tablename__ = "template_recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    datasource_id: Mapped[int] = mapped_column(ForeignKey("datasources.id"), nullable=False)
    message_sql_id: Mapped[int] = mapped_column(ForeignKey("message_sql.id"), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    sql_text: Mapped[str] = mapped_column(Text, nullable=False)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SystemPrompt(Base):
    __tablename__ = "system_prompts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    variables_schema: Mapped[Optional[dict]] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (UniqueConstraint("role", "version"),)


class SystemConfig(Base):
    __tablename__ = "system_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255))


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    datasource_id: Mapped[int] = mapped_column(ForeignKey("datasources.id"), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    messages: Mapped[list["Message"]] = relationship(back_populates="conversation")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    deep_think: Mapped[bool] = mapped_column(Boolean, default=False)
    execution_mode: Mapped[str] = mapped_column(String(32), default=ExecutionMode.AUTO.value)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
    sql_record: Mapped[Optional["MessageSql"]] = relationship(back_populates="message")


class MessageSql(Base):
    __tablename__ = "message_sql"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"), unique=True, nullable=False)
    sql_text: Mapped[str] = mapped_column(Text, nullable=False)
    was_executed: Mapped[bool] = mapped_column(Boolean, default=False)
    result_preview: Mapped[Optional[dict]] = mapped_column(JSON)

    message: Mapped["Message"] = relationship(back_populates="sql_record")


class RagDocument(Base):
    __tablename__ = "rag_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[Optional[int]] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    datasource_id: Mapped[Optional[int]] = mapped_column(ForeignKey("datasources.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    chunks: Mapped[list["RagChunk"]] = relationship(back_populates="document")


class RagChunk(Base):
    __tablename__ = "rag_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("rag_documents.id"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    qdrant_point_id: Mapped[Optional[str]] = mapped_column(String(64))

    document: Mapped["RagDocument"] = relationship(back_populates="chunks")
    quality_scores: Mapped[list["RagQualityScore"]] = relationship(back_populates="chunk")


class RagQualityScore(Base):
    __tablename__ = "rag_quality_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chunk_id: Mapped[int] = mapped_column(ForeignKey("rag_chunks.id"), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    session_id: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    chunk: Mapped["RagChunk"] = relationship(back_populates="quality_scores")


class RagAlert(Base):
    __tablename__ = "rag_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chunk_id: Mapped[int] = mapped_column(ForeignKey("rag_chunks.id"), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class LlmCacheEntry(Base):
    __tablename__ = "llm_cache_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cache_key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    response: Mapped[str] = mapped_column(Text, nullable=False)
    token_saved: Mapped[int] = mapped_column(Integer, default=0)
    embedding: Mapped[Optional[list]] = mapped_column(JSON)
    prompt_version: Mapped[Optional[int]] = mapped_column(Integer)
    ttl_seconds: Mapped[int] = mapped_column(Integer, default=86400)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class LlmCacheHitLog(Base):
    __tablename__ = "llm_cache_hit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(64))
    cache_entry_id: Mapped[Optional[int]] = mapped_column(ForeignKey("llm_cache_entries.id"))
    hit_type: Mapped[str] = mapped_column(String(16), nullable=False)
    saved_tokens: Mapped[int] = mapped_column(Integer, default=0)
    similarity: Mapped[Optional[float]] = mapped_column(Float)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
