"""Tests for SQL validation and schema graph."""

import pytest

from backend.sql.schema import SchemaGraph, SqlValidator


@pytest.fixture
def schema_graph():
    g = SchemaGraph()
    g.add_table(1, "users", True)
    g.add_table(2, "orders", True)
    g.add_fk("orders", "user_id", "users", "id")
    return g


def test_find_join_paths(schema_graph):
    paths = schema_graph.find_join_paths(["orders", "users"])
    assert len(paths) >= 1
    assert "orders.user_id = users.id" in paths[0]


def test_validate_select_only(schema_graph):
    validator = SqlValidator(schema_graph.allowed_tables, schema_graph)
    result = validator.validate("SELECT * FROM users")
    assert result.valid
    assert "LIMIT" in result.sql.upper()


def test_reject_non_select(schema_graph):
    validator = SqlValidator(schema_graph.allowed_tables, schema_graph)
    result = validator.validate("DELETE FROM users")
    assert not result.valid


def test_reject_disallowed_table(schema_graph):
    validator = SqlValidator(schema_graph.allowed_tables, schema_graph)
    result = validator.validate("SELECT * FROM secret_table")
    assert not result.valid
    assert any("whitelist" in e for e in result.errors)


def test_build_schema_context(schema_graph):
    tables = [{"table_name": "users", "description": "用户表"}]
    columns = [
        {
            "table_name": "users",
            "column_name": "id",
            "data_type": "INT",
            "description": "用户ID",
            "is_blacklisted": False,
        }
    ]
    ctx = schema_graph.build_schema_context(tables, columns, ["users"])
    assert "users" in ctx
    assert "id" in ctx
