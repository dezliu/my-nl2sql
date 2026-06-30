"""Tests for index_item / unindex_item (IndexPipeline mocked)."""

from unittest.mock import AsyncMock, patch

import pytest

from backend.db.models import TableMetadata
from backend.rag.index_ops import index_item, unindex_item


@pytest.mark.asyncio
async def test_index_item_table(patch_db, seeded_db, mock_index_pipeline):
    table_id = seeded_db["table"].id
    async with patch_db() as session:
        ok = await index_item(session, "table_metadata", table_id)
        assert ok is True
        table = await session.get(TableMetadata, table_id)
        assert table is not None
        assert table.is_indexed is True


@pytest.mark.asyncio
async def test_unindex_item_unknown_type(patch_db):
    async with patch_db() as session:
        ok = await unindex_item(session, "unknown_type", 1)
        assert ok is False


@pytest.mark.asyncio
async def test_index_item_unknown_type(patch_db):
    async with patch_db() as session:
        ok = await index_item(session, "unknown_type", 1)
        assert ok is False


@pytest.mark.asyncio
async def test_index_knowledge(patch_db, seeded_db):
    entry_id = seeded_db["knowledge"].id
    with patch("backend.rag.index_ops.IndexPipeline") as mock_cls:
        mock_cls.return_value.index_knowledge = AsyncMock(return_value=True)
        async with patch_db() as session:
            ok = await index_item(session, "knowledge", entry_id)
            assert ok is True
