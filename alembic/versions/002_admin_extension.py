"""admin extension: knowledge, template recommendations, is_indexed

Revision ID: 002
Revises: 001
Create Date: 2026-06-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "table_metadata",
        sa.Column("is_indexed", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "sql_templates",
        sa.Column("is_indexed", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "business_glossary",
        sa.Column("is_indexed", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )

    op.create_table(
        "knowledge_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("datasource_id", sa.Integer(), nullable=True),
        sa.Column("category", sa.String(64), nullable=False, server_default="faq"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_indexed", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.ForeignKeyConstraint(["datasource_id"], ["datasources.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "template_recommendations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("datasource_id", sa.Integer(), nullable=False),
        sa.Column("message_sql_id", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("sql_text", sa.Text(), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.ForeignKeyConstraint(["datasource_id"], ["datasources.id"]),
        sa.ForeignKeyConstraint(["message_sql_id"], ["message_sql.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("template_recommendations")
    op.drop_table("knowledge_entries")
    op.drop_column("business_glossary", "is_indexed")
    op.drop_column("sql_templates", "is_indexed")
    op.drop_column("table_metadata", "is_indexed")
