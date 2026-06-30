"use client";

import { gql, useMutation, useQuery } from "@apollo/client";
import { useState } from "react";

const DATASOURCES = gql`
  query Datasources {
    datasources {
      id
      name
    }
  }
`;

const TABLES_DETAIL = gql`
  query TablesDetail($datasourceId: Int!) {
    tablesDetail(datasourceId: $datasourceId) {
      id
      tableName
      description
      isAllowed
      isIndexed
    }
  }
`;

const COLUMNS = gql`
  query Columns($tableId: Int!) {
    columns(tableId: $tableId) {
      id
      columnName
      dataType
      description
      isBlacklisted
    }
  }
`;

const FKS = gql`
  query FkRelationships($datasourceId: Int!) {
    fkRelationships(datasourceId: $datasourceId) {
      id
      fromTableId
      fromColumn
      toTableId
      toColumn
    }
  }
`;

const CREATE_TABLE = gql`
  mutation CreateTable($input: CreateTableInput!) {
    createTable(input: $input) {
      id
      tableName
    }
  }
`;

const UPDATE_TABLE = gql`
  mutation UpdateTable($input: UpdateTableInput!) {
    updateTable(input: $input) {
      id
    }
  }
`;

const DELETE_TABLE = gql`
  mutation DeleteTable($tableId: Int!) {
    deleteTable(tableId: $tableId)
  }
`;

const CREATE_COLUMN = gql`
  mutation CreateColumn($input: CreateColumnInput!) {
    createColumn(input: $input) {
      id
    }
  }
`;

const DELETE_COLUMN = gql`
  mutation DeleteColumn($columnId: Int!) {
    deleteColumn(columnId: $columnId)
  }
`;

const CREATE_FK = gql`
  mutation CreateFk($input: CreateFkInput!) {
    createFk(input: $input) {
      id
    }
  }
`;

const DELETE_FK = gql`
  mutation DeleteFk($fkId: Int!) {
    deleteFk(fkId: $fkId)
  }
`;

const INDEX_ITEM = gql`
  mutation IndexItem($input: IndexItemInput!) {
    indexItem(input: $input)
  }
`;

const UNINDEX_ITEM = gql`
  mutation UnindexItem($input: IndexItemInput!) {
    unindexItem(input: $input)
  }
`;

const INDEX_DATASOURCE = gql`
  mutation IndexDatasource($datasourceId: Int!) {
    indexDatasource(datasourceId: $datasourceId)
  }
`;

export default function MetadataPage() {
  const [selectedDs, setSelectedDs] = useState<number | null>(null);
  const [selectedTable, setSelectedTable] = useState<number | null>(null);
  const [newTable, setNewTable] = useState({ tableName: "", description: "" });
  const [newColumn, setNewColumn] = useState({ columnName: "", dataType: "VARCHAR", description: "" });
  const [newFk, setNewFk] = useState({ fromTableId: 0, fromColumn: "", toTableId: 0, toColumn: "" });

  const { data: dsData } = useQuery(DATASOURCES);
  const { data: tablesData, refetch: refetchTables } = useQuery(TABLES_DETAIL, {
    variables: { datasourceId: selectedDs },
    skip: !selectedDs,
  });
  const { data: columnsData, refetch: refetchColumns } = useQuery(COLUMNS, {
    variables: { tableId: selectedTable },
    skip: !selectedTable,
  });
  const { data: fksData, refetch: refetchFks } = useQuery(FKS, {
    variables: { datasourceId: selectedDs },
    skip: !selectedDs,
  });

  const [createTable] = useMutation(CREATE_TABLE);
  const [updateTable] = useMutation(UPDATE_TABLE);
  const [deleteTable] = useMutation(DELETE_TABLE);
  const [createColumn] = useMutation(CREATE_COLUMN);
  const [deleteColumn] = useMutation(DELETE_COLUMN);
  const [createFk] = useMutation(CREATE_FK);
  const [deleteFk] = useMutation(DELETE_FK);
  const [indexItem] = useMutation(INDEX_ITEM);
  const [unindexItem] = useMutation(UNINDEX_ITEM);
  const [indexDatasource, { loading: indexing }] = useMutation(INDEX_DATASOURCE);

  const datasources = dsData?.datasources || [];
  const tables = tablesData?.tablesDetail || [];
  const columns = columnsData?.columns || [];
  const fks = fksData?.fkRelationships || [];

  const handleCreateTable = async () => {
    if (!selectedDs || !newTable.tableName) return;
    await createTable({
      variables: {
        input: {
          datasourceId: selectedDs,
          tableName: newTable.tableName,
          description: newTable.description || null,
        },
      },
    });
    setNewTable({ tableName: "", description: "" });
    refetchTables();
  };

  const handleToggleIndex = async (tableId: number, indexed: boolean) => {
    const input = { docType: "table_metadata", sourceId: tableId };
    if (indexed) {
      await unindexItem({ variables: { input } });
    } else {
      await indexItem({ variables: { input } });
    }
    refetchTables();
  };

  const handleCreateColumn = async () => {
    if (!selectedTable || !newColumn.columnName) return;
    await createColumn({
      variables: {
        input: {
          tableId: selectedTable,
          columnName: newColumn.columnName,
          dataType: newColumn.dataType,
          description: newColumn.description || null,
        },
      },
    });
    setNewColumn({ columnName: "", dataType: "VARCHAR", description: "" });
    refetchColumns();
  };

  const handleCreateFk = async () => {
    if (!selectedDs || !newFk.fromTableId || !newFk.toTableId) return;
    await createFk({
      variables: {
        input: {
          datasourceId: selectedDs,
          fromTableId: newFk.fromTableId,
          fromColumn: newFk.fromColumn,
          toTableId: newFk.toTableId,
          toColumn: newFk.toColumn,
        },
      },
    });
    refetchFks();
  };

  return (
    <div>
      <h1 className="page-title">元数据管理</h1>

      <div className="card">
        <div className="form-group">
          <label>数据源</label>
          <select
            value={selectedDs ?? ""}
            onChange={(e) => {
              setSelectedDs(Number(e.target.value));
              setSelectedTable(null);
            }}
          >
            <option value="">选择数据源</option>
            {datasources.map((ds: { id: number; name: string }) => (
              <option key={ds.id} value={ds.id}>
                {ds.name}
              </option>
            ))}
          </select>
        </div>
        <button
          className="btn"
          onClick={() => selectedDs && indexDatasource({ variables: { datasourceId: selectedDs } })}
          disabled={!selectedDs || indexing}
        >
          {indexing ? "索引中..." : "重建全量 RAG 索引"}
        </button>
      </div>

      {selectedDs && (
        <>
          <div className="card">
            <h3>新建表</h3>
            <div className="form-row">
              <input
                placeholder="表名"
                value={newTable.tableName}
                onChange={(e) => setNewTable({ ...newTable, tableName: e.target.value })}
              />
              <input
                placeholder="描述"
                value={newTable.description}
                onChange={(e) => setNewTable({ ...newTable, description: e.target.value })}
              />
              <button className="btn" onClick={handleCreateTable}>
                添加
              </button>
            </div>
          </div>

          <div className="card">
            <h3>表列表</h3>
            <table>
              <thead>
                <tr>
                  <th>表名</th>
                  <th>描述</th>
                  <th>允许查询</th>
                  <th>已索引</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {tables.map(
                  (t: {
                    id: number;
                    tableName: string;
                    description: string;
                    isAllowed: boolean;
                    isIndexed: boolean;
                  }) => (
                    <tr key={t.id}>
                      <td>
                        <button className="link-btn" onClick={() => setSelectedTable(t.id)}>
                          {t.tableName}
                        </button>
                      </td>
                      <td>{t.description || "-"}</td>
                      <td>{t.isAllowed ? "是" : "否"}</td>
                      <td>{t.isIndexed ? "是" : "否"}</td>
                      <td>
                        <button
                          className="btn btn-sm"
                          onClick={() =>
                            updateTable({
                              variables: { input: { id: t.id, isAllowed: !t.isAllowed } },
                            }).then(() => refetchTables())
                          }
                        >
                          切换允许
                        </button>
                        <button
                          className="btn btn-sm"
                          style={{ marginLeft: "0.5rem" }}
                          onClick={() => handleToggleIndex(t.id, t.isIndexed)}
                        >
                          {t.isIndexed ? "取消索引" : "入库"}
                        </button>
                        <button
                          className="btn btn-sm"
                          style={{ marginLeft: "0.5rem" }}
                          onClick={() =>
                            deleteTable({ variables: { tableId: t.id } }).then(() => refetchTables())
                          }
                        >
                          删除
                        </button>
                      </td>
                    </tr>
                  )
                )}
              </tbody>
            </table>
          </div>

          {selectedTable && (
            <div className="card">
              <h3>列管理</h3>
              <div className="form-row">
                <input
                  placeholder="列名"
                  value={newColumn.columnName}
                  onChange={(e) => setNewColumn({ ...newColumn, columnName: e.target.value })}
                />
                <input
                  placeholder="类型"
                  value={newColumn.dataType}
                  onChange={(e) => setNewColumn({ ...newColumn, dataType: e.target.value })}
                />
                <button className="btn" onClick={handleCreateColumn}>
                  添加列
                </button>
              </div>
              <table>
                <thead>
                  <tr>
                    <th>列名</th>
                    <th>类型</th>
                    <th>描述</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {columns.map(
                    (c: { id: number; columnName: string; dataType: string; description: string }) => (
                      <tr key={c.id}>
                        <td>{c.columnName}</td>
                        <td>{c.dataType}</td>
                        <td>{c.description || "-"}</td>
                        <td>
                          <button
                            className="btn btn-sm"
                            onClick={() =>
                              deleteColumn({ variables: { columnId: c.id } }).then(() =>
                                refetchColumns()
                              )
                            }
                          >
                            删除
                          </button>
                        </td>
                      </tr>
                    )
                  )}
                </tbody>
              </table>
            </div>
          )}

          <div className="card">
            <h3>外键关系</h3>
            <div className="form-row">
              <input
                type="number"
                placeholder="源表 ID"
                value={newFk.fromTableId || ""}
                onChange={(e) => setNewFk({ ...newFk, fromTableId: Number(e.target.value) })}
              />
              <input
                placeholder="源列"
                value={newFk.fromColumn}
                onChange={(e) => setNewFk({ ...newFk, fromColumn: e.target.value })}
              />
              <input
                type="number"
                placeholder="目标表 ID"
                value={newFk.toTableId || ""}
                onChange={(e) => setNewFk({ ...newFk, toTableId: Number(e.target.value) })}
              />
              <input
                placeholder="目标列"
                value={newFk.toColumn}
                onChange={(e) => setNewFk({ ...newFk, toColumn: e.target.value })}
              />
              <button className="btn" onClick={handleCreateFk}>
                添加 FK
              </button>
            </div>
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>源表→列</th>
                  <th>目标表→列</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {fks.map(
                  (f: {
                    id: number;
                    fromTableId: number;
                    fromColumn: string;
                    toTableId: number;
                    toColumn: string;
                  }) => (
                    <tr key={f.id}>
                      <td>{f.id}</td>
                      <td>
                        {f.fromTableId}.{f.fromColumn}
                      </td>
                      <td>
                        {f.toTableId}.{f.toColumn}
                      </td>
                      <td>
                        <button
                          className="btn btn-sm"
                          onClick={() =>
                            deleteFk({ variables: { fkId: f.id } }).then(() => refetchFks())
                          }
                        >
                          删除
                        </button>
                      </td>
                    </tr>
                  )
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
