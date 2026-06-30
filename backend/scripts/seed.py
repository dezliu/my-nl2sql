"""Seed script for development data."""

import asyncio

from backend.db.models import Datasource, TableMetadata, ColumnMetadata, FkRelationship, SqlTemplate, BusinessGlossary
from backend.db.prompts import seed_default_prompts
from backend.db.system_config import seed_default_system_configs
from backend.db.session import async_session_factory, engine
from backend.eval.rag_eval import import_cases_from_json


async def seed():
    async with async_session_factory() as session:
        await seed_default_prompts(session)
        await seed_default_system_configs(session)

        ds = Datasource(
            name="Demo DB",
            connection_url="mysql://nl2sql:nl2sql@localhost:3307/nl2sql",
            is_active=True,
        )
        session.add(ds)
        await session.flush()

        users = TableMetadata(datasource_id=ds.id, table_name="users", description="用户表", is_allowed=True)
        orders = TableMetadata(datasource_id=ds.id, table_name="orders", description="订单表", is_allowed=True)
        session.add_all([users, orders])
        await session.flush()

        session.add_all([
            ColumnMetadata(table_id=users.id, column_name="id", data_type="INT", description="用户ID"),
            ColumnMetadata(table_id=users.id, column_name="username", data_type="VARCHAR", description="用户名"),
            ColumnMetadata(table_id=orders.id, column_name="id", data_type="INT", description="订单ID"),
            ColumnMetadata(table_id=orders.id, column_name="user_id", data_type="INT", description="用户ID"),
            ColumnMetadata(table_id=orders.id, column_name="amount", data_type="DECIMAL", description="金额"),
        ])

        session.add(FkRelationship(
            datasource_id=ds.id,
            from_table_id=orders.id,
            from_column="user_id",
            to_table_id=users.id,
            to_column="id",
        ))

        session.add(SqlTemplate(
            datasource_id=ds.id,
            question="查询每个用户的订单总数",
            sql_text="SELECT u.username, COUNT(o.id) as order_count FROM users u JOIN orders o ON u.id = o.user_id GROUP BY u.username",
        ))

        session.add(BusinessGlossary(
            term="GMV",
            definition="成交总额，所有订单金额之和",
            aliases="成交额,总销售额",
        ))

        await session.commit()
        imported, skipped = await import_cases_from_json(session)
        print(f"Seeded datasource id={ds.id}")
        print(f"RAG eval benchmark: imported {imported}, skipped {skipped}")


async def main() -> None:
    await seed()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
