"""Introspect remote MySQL schema via INFORMATION_SCHEMA."""

from dataclasses import dataclass, field

from backend.sql.connection import connect_mysql, parse_db


@dataclass
class ScannedColumn:
    column_name: str
    data_type: str
    description: str | None = None
    is_nullable: bool = True


@dataclass
class ScannedForeignKey:
    from_table: str
    from_column: str
    to_table: str
    to_column: str


@dataclass
class ScannedTable:
    table_name: str
    table_comment: str | None = None
    columns: list[ScannedColumn] = field(default_factory=list)


@dataclass
class IntrospectionResult:
    tables: list[ScannedTable]
    foreign_keys: list[ScannedForeignKey]


async def introspect_mysql(connection_url: str) -> IntrospectionResult:
    schema = parse_db(connection_url)
    if not schema:
        raise ValueError("连接 URL 中未指定数据库名")

    try:
        conn = await connect_mysql(connection_url)
    except Exception as e:
        raise ValueError(f"无法连接数据源: {e}") from e

    try:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT TABLE_NAME, TABLE_COMMENT
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_NAME
                """,
                (schema,),
            )
            table_rows = await cur.fetchall()

            await cur.execute(
                """
                SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_COMMENT
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = %s
                ORDER BY TABLE_NAME, ORDINAL_POSITION
                """,
                (schema,),
            )
            column_rows = await cur.fetchall()

            await cur.execute(
                """
                SELECT
                    kcu.TABLE_NAME AS from_table,
                    kcu.COLUMN_NAME AS from_column,
                    kcu.REFERENCED_TABLE_NAME AS to_table,
                    kcu.REFERENCED_COLUMN_NAME AS to_column
                FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                INNER JOIN INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
                    ON kcu.CONSTRAINT_SCHEMA = rc.CONSTRAINT_SCHEMA
                    AND kcu.CONSTRAINT_NAME = rc.CONSTRAINT_NAME
                WHERE kcu.TABLE_SCHEMA = %s
                    AND kcu.REFERENCED_TABLE_NAME IS NOT NULL
                ORDER BY kcu.TABLE_NAME, kcu.ORDINAL_POSITION
                """,
                (schema,),
            )
            fk_rows = await cur.fetchall()
    finally:
        conn.close()

    columns_by_table: dict[str, list[ScannedColumn]] = {}
    for table_name, column_name, column_type, is_nullable, column_comment in column_rows:
        columns_by_table.setdefault(table_name, []).append(
            ScannedColumn(
                column_name=column_name,
                data_type=column_type,
                description=column_comment or None,
                is_nullable=is_nullable == "YES",
            )
        )

    tables = [
        ScannedTable(
            table_name=table_name,
            table_comment=table_comment or None,
            columns=columns_by_table.get(table_name, []),
        )
        for table_name, table_comment in table_rows
    ]

    foreign_keys = [
        ScannedForeignKey(
            from_table=from_table,
            from_column=from_column,
            to_table=to_table,
            to_column=to_column,
        )
        for from_table, from_column, to_table, to_column in fk_rows
    ]

    return IntrospectionResult(tables=tables, foreign_keys=foreign_keys)
