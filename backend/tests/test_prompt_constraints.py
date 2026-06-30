"""Tests for anti-hallucination prompt constraints and cannot_answer routing."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.db.models import PromptRole
from backend.db.prompts import DEFAULT_PROMPTS
from backend.graph.workflow import (
    _format_allowed_tables,
    _format_prompt,
    route_after_sql_generate,
    sql_generate,
)


def test_sql_generator_prompt_includes_allowed_tables():
    template = DEFAULT_PROMPTS[PromptRole.SQL_GENERATOR.value]
    prompt = _format_prompt(
        template,
        question="近7天销售额",
        schema_context="## Schema Context\n### Table: users",
        chunks="",
        safety_rules="SELECT only; include LIMIT",
        allowed_tables="orders, users",
    )
    assert "orders, users" in prompt
    assert "cannot_answer" in prompt
    assert "Do NOT invent" in prompt


def test_query_expander_forbids_inventing_tables():
    template = DEFAULT_PROMPTS[PromptRole.QUERY_EXPANDER.value]
    prompt = _format_prompt(
        template,
        question="近7天销售额",
        intent="query_data",
        allowed_tables="orders, users",
    )
    assert "orders, users" in prompt
    assert "Do NOT invent" in prompt


def test_format_allowed_tables_sorted():
    state = {"allowed_tables": {"orders", "users"}}
    assert _format_allowed_tables(state) == "orders, users"


def test_route_after_sql_generate():
    assert route_after_sql_generate({"cannot_answer": True}) == "finalize"
    assert route_after_sql_generate({"cannot_answer": False}) == "sql_safety"
    assert route_after_sql_generate({}) == "sql_safety"


@pytest.mark.asyncio
async def test_sql_generate_cannot_answer_emits_summary():
    llm_service = MagicMock()
    llm_service.astream = AsyncMock(
        return_value=(
            '{"sql": null, "explanation": "当前数据源无 sales 表", "cannot_answer": true}',
            "none",
        )
    )
    state = {
        "question": "近7天销售额",
        "allowed_tables": {"users", "orders"},
        "schema_context": "## Table: users",
        "system_prompts": {"sql_generator": DEFAULT_PROMPTS[PromptRole.SQL_GENERATOR.value]},
        "rag_chunks": [],
        "deep_think": False,
    }
    result = await sql_generate(state, llm_service)
    assert result["cannot_answer"] is True
    assert result["generated_sql"] == ""
    assert "sales" in result["summary"]
    event_types = [e["type"] for e in result["stream_events"]]
    assert "SUMMARY" in event_types
    assert "SQL" not in event_types
