"""FK graph, JOIN path discovery, SQL validation and execution."""

from dataclasses import dataclass

import networkx as nx
import sqlglot
from sqlglot import exp

from backend.config import settings
from backend.sql.connection import connect_mysql


@dataclass
class JoinEdge:
    from_table: str
    from_column: str
    to_table: str
    to_column: str


@dataclass
class ValidationResult:
    valid: bool
    sql: str
    errors: list[str]


class SchemaGraph:
    def __init__(self) -> None:
        self.graph = nx.Graph()
        self.table_names: dict[int, str] = {}
        self.allowed_tables: set[str] = set()

    def add_table(self, table_id: int, name: str, allowed: bool = True) -> None:
        self.table_names[table_id] = name
        self.graph.add_node(name)
        if allowed:
            self.allowed_tables.add(name)

    def add_fk(self, from_table: str, from_col: str, to_table: str, to_col: str) -> None:
        self.graph.add_edge(
            from_table,
            to_table,
            join=f"{from_table}.{from_col} = {to_table}.{to_col}",
            from_column=from_col,
            to_column=to_col,
        )

    def find_join_paths(self, tables: list[str]) -> list[str]:
        if len(tables) <= 1:
            return []
        paths: list[str] = []
        for i in range(len(tables) - 1):
            try:
                path = nx.shortest_path(self.graph, tables[i], tables[i + 1])
                for j in range(len(path) - 1):
                    edge_data = self.graph.get_edge_data(path[j], path[j + 1])
                    if edge_data and "join" in edge_data:
                        paths.append(edge_data["join"])
            except nx.NetworkXNoPath:
                continue
        return list(dict.fromkeys(paths))

    def build_schema_context(
        self,
        tables: list[dict],
        columns: list[dict],
        relevant_table_names: list[str],
    ) -> str:
        lines = ["## Schema Context"]
        for t in tables:
            if t["table_name"] not in relevant_table_names:
                continue
            lines.append(f"\n### Table: {t['table_name']}")
            if t.get("description"):
                lines.append(f"Description: {t['description']}")
            table_cols = [c for c in columns if c["table_name"] == t["table_name"]]
            for c in table_cols:
                if c.get("is_blacklisted"):
                    continue
                desc = f" - {c['description']}" if c.get("description") else ""
                lines.append(f"  - {c['column_name']} ({c['data_type']}){desc}")

        join_paths = self.find_join_paths(relevant_table_names)
        if join_paths:
            lines.append("\n## Recommended JOIN paths:")
            for jp in join_paths:
                lines.append(f"  - {jp}")
        return "\n".join(lines)


class SqlValidator:
    def __init__(self, allowed_tables: set[str], schema_graph: SchemaGraph) -> None:
        self.allowed_tables = allowed_tables
        self.schema_graph = schema_graph

    def validate(self, sql: str) -> ValidationResult:
        errors: list[str] = []
        try:
            statements = sqlglot.parse(sql, read="mysql")
        except Exception as e:
            return ValidationResult(valid=False, sql=sql, errors=[f"Parse error: {e}"])

        if len(statements) != 1:
            return ValidationResult(valid=False, sql=sql, errors=["Only single SELECT allowed"])

        stmt = statements[0]
        if not isinstance(stmt, exp.Select):
            return ValidationResult(valid=False, sql=sql, errors=["Only SELECT statements allowed"])

        referenced = self._extract_tables(stmt)
        for table in referenced:
            if table not in self.allowed_tables:
                errors.append(f"Table '{table}' not in whitelist")

        if not self._has_limit(stmt):
            sql = f"{sql.rstrip(';')} LIMIT {settings.default_sql_limit}"

        return ValidationResult(valid=len(errors) == 0, sql=sql, errors=errors)

    def _extract_tables(self, stmt: exp.Expression) -> set[str]:
        tables: set[str] = set()
        for table in stmt.find_all(exp.Table):
            if table.name:
                tables.add(table.name)
        return tables

    def _has_limit(self, stmt: exp.Select) -> bool:
        return stmt.args.get("limit") is not None


async def execute_sql(connection_url: str, sql: str, limit: int = 100) -> dict:
    """Execute validated SQL against datasource (read-only)."""
    import aiomysql

    conn = await connect_mysql(connection_url)
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(sql)
            rows = await cur.fetchmany(limit)
            columns = [d[0] for d in cur.description] if cur.description else []
            return {"columns": columns, "rows": rows, "row_count": len(rows)}
    finally:
        conn.close()
