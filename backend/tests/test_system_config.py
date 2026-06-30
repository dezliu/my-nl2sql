"""Tests for DB-backed system configuration."""

import pytest

from backend.config import settings
from backend.db.system_config import (
    SQL_ROW_LIMIT_KEY,
    get_sql_row_limit,
    seed_default_system_configs,
    set_sql_row_limit,
)
from backend.db.models import SystemConfig


@pytest.mark.asyncio
async def test_get_sql_row_limit_fallback(patch_db):
    async with patch_db() as session:
        assert await get_sql_row_limit(session) == settings.default_sql_limit


@pytest.mark.asyncio
async def test_set_and_get_sql_row_limit(patch_db):
    async with patch_db() as session:
        await set_sql_row_limit(session, 500)
        assert await get_sql_row_limit(session) == 500


@pytest.mark.asyncio
async def test_set_sql_row_limit_rejects_invalid(patch_db):
    async with patch_db() as session:
        with pytest.raises(ValueError):
            await set_sql_row_limit(session, 0)


@pytest.mark.asyncio
async def test_seed_default_system_configs_idempotent(patch_db):
    async with patch_db() as session:
        await seed_default_system_configs(session)
        await seed_default_system_configs(session)
        from sqlalchemy import select

        result = await session.execute(
            select(SystemConfig).where(SystemConfig.key == SQL_ROW_LIMIT_KEY)
        )
        rows = result.scalars().all()
        assert len(rows) == 1
        assert int(rows[0].value) == settings.default_sql_limit
