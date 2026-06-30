"""System configuration helpers (DB-backed with env fallback)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.db.models import SystemConfig

SQL_ROW_LIMIT_KEY = "sql_row_limit"
SQL_ROW_LIMIT_DESCRIPTION = "SQL 查询默认最大返回行数（Prompt 要求与校验兜底共用）"


async def get_config_value(session: AsyncSession, key: str) -> str | None:
    result = await session.execute(select(SystemConfig).where(SystemConfig.key == key))
    row = result.scalar_one_or_none()
    return row.value if row else None


async def get_sql_row_limit(session: AsyncSession) -> int:
    raw = await get_config_value(session, SQL_ROW_LIMIT_KEY)
    if raw is not None:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return settings.default_sql_limit


async def set_sql_row_limit(session: AsyncSession, limit: int) -> SystemConfig:
    if limit <= 0:
        raise ValueError("SQL 行数限制必须大于 0")
    result = await session.execute(
        select(SystemConfig).where(SystemConfig.key == SQL_ROW_LIMIT_KEY)
    )
    row = result.scalar_one_or_none()
    if row:
        row.value = str(limit)
    else:
        row = SystemConfig(
            key=SQL_ROW_LIMIT_KEY,
            value=str(limit),
            description=SQL_ROW_LIMIT_DESCRIPTION,
        )
        session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def seed_default_system_configs(session: AsyncSession) -> None:
    result = await session.execute(
        select(SystemConfig).where(SystemConfig.key == SQL_ROW_LIMIT_KEY)
    )
    if result.scalar_one_or_none():
        return
    session.add(
        SystemConfig(
            key=SQL_ROW_LIMIT_KEY,
            value=str(settings.default_sql_limit),
            description=SQL_ROW_LIMIT_DESCRIPTION,
        )
    )
    await session.commit()
