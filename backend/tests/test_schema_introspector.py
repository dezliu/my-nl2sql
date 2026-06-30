"""Tests for MySQL schema introspector."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.schema_introspector import introspect_mysql


@pytest.mark.asyncio
async def test_introspect_mysql_maps_tables_columns_and_fks():
    mock_conn = MagicMock()
    mock_cur = AsyncMock()
    mock_conn.cursor.return_value.__aenter__ = AsyncMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__aexit__ = AsyncMock(return_value=False)
    mock_cur.fetchall.side_effect = [
        [("users", "用户表"), ("orders", "")],
        [
            ("users", "id", "int", "NO", "用户ID"),
            ("users", "username", "varchar(64)", "NO", ""),
            ("orders", "id", "int", "NO", ""),
            ("orders", "user_id", "int", "NO", ""),
        ],
        [("orders", "user_id", "users", "id")],
    ]

    with patch(
        "backend.services.schema_introspector.connect_mysql",
        AsyncMock(return_value=mock_conn),
    ):
        result = await introspect_mysql("mysql://u:p@localhost:3306/demo")

    assert len(result.tables) == 2
    users = next(t for t in result.tables if t.table_name == "users")
    assert users.table_comment == "用户表"
    assert len(users.columns) == 2
    assert users.columns[0].column_name == "id"
    assert users.columns[0].data_type == "int"
    assert users.columns[0].description == "用户ID"
    assert len(result.foreign_keys) == 1
    assert result.foreign_keys[0].from_table == "orders"
    assert result.foreign_keys[0].to_table == "users"


@pytest.mark.asyncio
async def test_introspect_mysql_raises_on_connection_failure():
    with patch(
        "backend.services.schema_introspector.connect_mysql",
        AsyncMock(side_effect=OSError("connection refused")),
    ):
        with pytest.raises(ValueError, match="无法连接数据源"):
            await introspect_mysql("mysql://u:p@localhost:3306/demo")
