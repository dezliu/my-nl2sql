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
