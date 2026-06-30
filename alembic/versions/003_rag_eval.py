"""rag eval tables: cases, runs, run items

Revision ID: 003
Revises: 002
Create Date: 2026-06-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rag_eval_cases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("datasource_id", sa.Integer(), nullable=True),
        sa.Column("expected_chunk_ids", sa.JSON(), nullable=True),
        sa.Column("expected_tables", sa.JSON(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.ForeignKeyConstraint(["datasource_id"], ["datasources.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "rag_eval_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("datasource_id", sa.Integer(), nullable=True),
        sa.Column("case_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recall_at_k", sa.Float(), nullable=True),
        sa.Column("mrr", sa.Float(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.ForeignKeyConstraint(["datasource_id"], ["datasources.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "rag_eval_run_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("case_id", sa.Integer(), nullable=False),
        sa.Column("recall", sa.Float(), nullable=False),
        sa.Column("mrr", sa.Float(), nullable=False),
        sa.Column("match_mode", sa.String(16), nullable=False),
        sa.Column("retrieved_chunk_ids", sa.JSON(), nullable=True),
        sa.Column("hit_chunk_ids", sa.JSON(), nullable=True),
        sa.Column("skipped", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("skip_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["case_id"], ["rag_eval_cases.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["rag_eval_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("rag_eval_run_items")
    op.drop_table("rag_eval_runs")
    op.drop_table("rag_eval_cases")
