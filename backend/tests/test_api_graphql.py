"""Tests for GraphQL Query/Mutation (no LLM calls)."""

import pytest

from backend.tests.conftest import gql


@pytest.mark.asyncio
async def test_graphql_health_query(client):
    data = await gql(client, "{ health { status version } }")
    assert data["health"]["status"] == "ok"


@pytest.mark.asyncio
async def test_graphql_datasources(client, seeded_db):
    data = await gql(client, "{ datasources { id name isActive } }")
    names = [d["name"] for d in data["datasources"]]
    assert seeded_db["datasource"].name in names


@pytest.mark.asyncio
async def test_graphql_tables_and_detail(client, seeded_db):
    ds_id = seeded_db["datasource"].id
    data = await gql(
        client,
        """
        query($id: Int!) {
          tables(datasourceId: $id) { tableName isAllowed }
          tablesDetail(datasourceId: $id) { tableName isIndexed }
        }
        """,
        {"id": ds_id},
    )
    assert data["tables"][0]["tableName"] == "users"
    assert data["tablesDetail"][0]["isIndexed"] is False


@pytest.mark.asyncio
async def test_graphql_business_and_templates(client, seeded_db):
    ds_id = seeded_db["datasource"].id
    data = await gql(
        client,
        """
        query($id: Int!) {
          businessGlossary { term definition isIndexed }
          knowledgeEntries(datasourceId: $id) { title category }
          sqlTemplates(datasourceId: $id) { question sqlText }
        }
        """,
        {"id": ds_id},
    )
    assert data["businessGlossary"][0]["term"] == "GMV"
    assert data["knowledgeEntries"][0]["title"] == "FAQ"
    assert "SELECT" in data["sqlTemplates"][0]["sqlText"]


@pytest.mark.asyncio
async def test_graphql_test_rag_search(client, mock_retriever):
    data = await gql(
        client,
        'query { testRagSearch(query: "users", topK: 3) { content score docType } }',
    )
    assert len(data["testRagSearch"]) == 1
    assert data["testRagSearch"][0]["docType"] == "table_metadata"
    mock_retriever.return_value.search.assert_called_once()


@pytest.mark.asyncio
async def test_graphql_create_table(client, seeded_db):
    ds_id = seeded_db["datasource"].id
    data = await gql(
        client,
        """
        mutation($input: CreateTableInput!) {
          createTable(input: $input) { tableName isAllowed isIndexed }
        }
        """,
        {"input": {"datasourceId": ds_id, "tableName": "orders", "description": "订单"}},
    )
    assert data["createTable"]["tableName"] == "orders"
    assert data["createTable"]["isIndexed"] is False


@pytest.mark.asyncio
async def test_graphql_create_column(client, seeded_db):
    table_id = seeded_db["table"].id
    data = await gql(
        client,
        """
        mutation($input: CreateColumnInput!) {
          createColumn(input: $input) { columnName dataType }
        }
        """,
        {
            "input": {
                "tableId": table_id,
                "columnName": "id",
                "dataType": "INT",
                "description": "主键",
            }
        },
    )
    assert data["createColumn"]["columnName"] == "id"


@pytest.mark.asyncio
async def test_graphql_glossary_crud(client, seeded_db):
    created = await gql(
        client,
        """
        mutation($input: CreateGlossaryInput!) {
          createGlossary(input: $input) { id term isIndexed }
        }
        """,
        {"input": {"term": "DAU", "definition": "日活"}},
    )
    assert created["createGlossary"]["term"] == "DAU"

    updated = await gql(
        client,
        """
        mutation($input: UpdateGlossaryInput!) {
          updateGlossary(input: $input) { definition }
        }
        """,
        {"input": {"id": created["createGlossary"]["id"], "definition": "日活跃用户"}},
    )
    assert updated["updateGlossary"]["definition"] == "日活跃用户"


@pytest.mark.asyncio
async def test_graphql_index_item(client, seeded_db, mock_index_pipeline):
    table_id = seeded_db["table"].id
    data = await gql(
        client,
        """
        mutation($input: IndexItemInput!) {
          indexItem(input: $input)
        }
        """,
        {"input": {"docType": "table_metadata", "sourceId": table_id}},
    )
    assert data["indexItem"] is True
    mock_index_pipeline.return_value.index_table.assert_called_once_with(table_id)


@pytest.mark.asyncio
async def test_graphql_ask_question_returns_session(client, seeded_db, mock_run_workflow):
    ds_id = seeded_db["datasource"].id
    data = await gql(
        client,
        """
        mutation($input: AskInput!) {
          askQuestion(input: $input) { sessionId }
        }
        """,
        {
            "input": {
                "question": "查询用户数",
                "datasourceId": ds_id,
                "deepThink": False,
                "executionMode": "GENERATE_ONLY",
            }
        },
    )
    assert data["askQuestion"]["sessionId"]


@pytest.mark.asyncio
async def test_graphql_create_and_delete_datasource(client, seeded_db):
    created = await gql(
        client,
        """
        mutation($input: CreateDatasourceInput!) {
          createDatasource(input: $input) { id name connectionUrl isActive }
        }
        """,
        {
            "input": {
                "name": "New DS",
                "connectionUrl": "mysql://u:p@localhost:3306/newdb",
            }
        },
    )
    assert created["createDatasource"]["name"] == "New DS"
    assert created["createDatasource"]["isActive"] is True
    new_id = created["createDatasource"]["id"]

    updated = await gql(
        client,
        """
        mutation($input: UpdateDatasourceInput!) {
          updateDatasource(input: $input) { id name }
        }
        """,
        {"input": {"id": new_id, "name": "Renamed DS"}},
    )
    assert updated["updateDatasource"]["name"] == "Renamed DS"

    data = await gql(client, "{ datasources { id name } }")
    assert any(d["id"] == new_id for d in data["datasources"])

    deleted = await gql(
        client,
        """
        mutation($id: Int!) {
          deleteDatasource(datasourceId: $id)
        }
        """,
        {"id": new_id},
    )
    assert deleted["deleteDatasource"] is True

    data = await gql(client, "{ datasources { id name } }")
    assert not any(d["id"] == new_id for d in data["datasources"])


@pytest.mark.asyncio
async def test_graphql_delete_datasource_cascades_metadata(client, seeded_db, mock_index_pipeline):
    ds_id = seeded_db["datasource"].id
    table_id = seeded_db["table"].id

    deleted = await gql(
        client,
        """
        mutation($id: Int!) {
          deleteDatasource(datasourceId: $id)
        }
        """,
        {"id": ds_id},
    )
    assert deleted["deleteDatasource"] is True

    data = await gql(
        client,
        """
        query($dsId: Int!, $tableId: Int!) {
          tablesDetail(datasourceId: $dsId) { id }
          columns(tableId: $tableId) { id }
        }
        """,
        {"dsId": ds_id, "tableId": table_id},
    )
    assert data["tablesDetail"] == []
    assert data["columns"] == []


@pytest.mark.asyncio
async def test_graphql_scan_datasource_tables(client, seeded_db, monkeypatch):
    from backend.services.schema_introspector import ScannedColumn, ScannedTable

    async def fake_scan(session, datasource_id, connection_url):
        return [
            (
                ScannedTable(
                    table_name="products",
                    table_comment="商品",
                    columns=[ScannedColumn("id", "int", None)],
                ),
                False,
                None,
            ),
            (
                ScannedTable(
                    table_name="users",
                    table_comment=None,
                    columns=[],
                ),
                True,
                seeded_db["table"].id,
            ),
        ]

    monkeypatch.setattr("backend.api.admin_graphql.scan_datasource_tables", fake_scan)
    ds_id = seeded_db["datasource"].id
    data = await gql(
        client,
        """
        query($id: Int!) {
          scanDatasourceTables(datasourceId: $id) {
            tableName
            columnCount
            alreadyExists
            existingTableId
          }
        }
        """,
        {"id": ds_id},
    )
    tables = data["scanDatasourceTables"]
    assert any(t["tableName"] == "products" and not t["alreadyExists"] for t in tables)
    assert any(t["tableName"] == "users" and t["alreadyExists"] for t in tables)


@pytest.mark.asyncio
async def test_graphql_sync_datasource_metadata(client, seeded_db, monkeypatch):
    from backend.services.metadata_sync import SyncResult

    async def fake_sync(session, datasource_id, connection_url, items, options, introspection=None):
        return SyncResult(
            tables_added=1,
            tables_updated=0,
            columns_added=2,
            columns_updated=0,
            fks_synced=1,
            indexed_count=1 if options.index_to_rag else 0,
        )

    monkeypatch.setattr("backend.api.admin_graphql.sync_datasource_metadata", fake_sync)
    ds_id = seeded_db["datasource"].id
    data = await gql(
        client,
        """
        mutation($input: SyncDatasourceMetadataInput!) {
          syncDatasourceMetadata(input: $input) {
            tablesAdded
            columnsAdded
            fksSynced
            indexedCount
          }
        }
        """,
        {
            "input": {
                "datasourceId": ds_id,
                "tables": [{"tableName": "products", "description": "商品表"}],
                "syncFks": True,
                "indexToRag": True,
            }
        },
    )
    result = data["syncDatasourceMetadata"]
    assert result["tablesAdded"] == 1
    assert result["fksSynced"] == 1
    assert result["indexedCount"] == 1


@pytest.mark.asyncio
async def test_graphql_index_datasource(client, seeded_db):
    from unittest.mock import AsyncMock, patch

    with patch("backend.api.schema.IndexPipeline") as mock_pipeline:
        mock_pipeline.return_value.index_all_for_datasource = AsyncMock(return_value=3)
        ds_id = seeded_db["datasource"].id
        data = await gql(
            client,
            """
            mutation($id: Int!) {
              indexDatasource(datasourceId: $id)
            }
            """,
            {"id": ds_id},
        )
        assert data["indexDatasource"] == 3
