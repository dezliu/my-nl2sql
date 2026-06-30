"use client";

import { gql, useMutation, useQuery } from "@apollo/client";
import { useEffect, useState } from "react";

import { AdminErrorBanner } from "../../../components/AdminErrorBanner";
import { SyncTablesModal } from "../../../components/SyncTablesModal";
import { parseConnectionUrl } from "../../../lib/connection-url";
import { formatMutationError } from "../../../lib/mutation-error";

const DATASOURCES = gql`
  query Datasources {
    datasources {
      id
      name
      connectionUrl
      isActive
    }
  }
`;

const CREATE_DATASOURCE = gql`
  mutation CreateDatasource($input: CreateDatasourceInput!) {
    createDatasource(input: $input) {
      id
      name
    }
  }
`;

const DELETE_DATASOURCE = gql`
  mutation DeleteDatasource($datasourceId: Int!) {
    deleteDatasource(datasourceId: $datasourceId)
  }
`;

const UPDATE_DATASOURCE = gql`
  mutation UpdateDatasource($input: UpdateDatasourceInput!) {
    updateDatasource(input: $input) {
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
  const [newDatasource, setNewDatasource] = useState({ name: "", connectionUrl: "" });
  const [editDsName, setEditDsName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [newTable, setNewTable] = useState({ tableName: "", description: "" });
  const [newColumn, setNewColumn] = useState({ columnName: "", dataType: "VARCHAR", description: "" });
  const [newFk, setNewFk] = useState({ fromTableId: 0, fromColumn: "", toTableId: 0, toColumn: "" });
  const [syncModalOpen, setSyncModalOpen] = useState(false);

  const { data: dsData, refetch: refetchDatasources } = useQuery(DATASOURCES);
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

  const [createDatasource] = useMutation(CREATE_DATASOURCE);
  const [updateDatasource] = useMutation(UPDATE_DATASOURCE);
  const [deleteDatasource] = useMutation(DELETE_DATASOURCE);
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
  const selectedDatasource = datasources.find(
    (ds: { id: number; name: string; connectionUrl: string }) => ds.id === selectedDs
  );
  const parsedConnection = selectedDatasource?.connectionUrl
    ? parseConnectionUrl(selectedDatasource.connectionUrl)
    : null;

  useEffect(() => {
    setEditDsName(selectedDatasource?.name ?? "");
  }, [selectedDs, selectedDatasource?.name]);

  const handleCreateDatasource = async () => {
    if (!newDatasource.name.trim() || !newDatasource.connectionUrl.trim()) return;
    setError(null);
    try {
      const { data } = await createDatasource({
        variables: {
          input: {
            name: newDatasource.name.trim(),
            connectionUrl: newDatasource.connectionUrl.trim(),
          },
        },
      });
      setNewDatasource({ name: "", connectionUrl: "" });
      await refetchDatasources();
      if (data?.createDatasource?.id) {
        setSelectedDs(data.createDatasource.id);
        setSelectedTable(null);
        setSyncModalOpen(true);
      }
    } catch (err) {
      setError(formatMutationError(err));
    }
  };

  const handleUpdateDatasourceName = async () => {
    if (!selectedDs || !editDsName.trim()) return;
    if (editDsName.trim() === selectedDatasource?.name) return;
    setError(null);
    try {
      await updateDatasource({
        variables: { input: { id: selectedDs, name: editDsName.trim() } },
      });
      await refetchDatasources();
    } catch (err) {
      setError(formatMutationError(err));
    }
  };

  const handleDeleteDatasource = async () => {
    if (!selectedDs) return;
    const ds = datasources.find((d: { id: number; name: string }) => d.id === selectedDs);
    const label = ds?.name ?? `ID ${selectedDs}`;
    if (!window.confirm(`确定删除数据源「${label}」？将同时删除其表、列、外键、模板、知识库条目及 RAG 索引。`)) {
      return;
    }
    setError(null);
    try {
      await deleteDatasource({ variables: { datasourceId: selectedDs } });
      setSelectedDs(null);
      setSelectedTable(null);
      await refetchDatasources();
    } catch (err) {
      setError(formatMutationError(err));
    }
  };

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
      <AdminErrorBanner message={error} onDismiss={() => setError(null)} />

      <div className="card">
        <h3>数据源</h3>
        <div className="form-row">
          <input
            placeholder="名称"
            value={newDatasource.name}
            onChange={(e) => setNewDatasource({ ...newDatasource, name: e.target.value })}
          />
          <input
            placeholder="连接 URL（如 mysql://user:pass@host:3306/db）"
            value={newDatasource.connectionUrl}
            onChange={(e) =>
              setNewDatasource({ ...newDatasource, connectionUrl: e.target.value })
            }
            style={{ flex: 2 }}
          />
          <button className="btn" onClick={handleCreateDatasource}>
            新增数据源
          </button>
        </div>
        <div className="form-group" style={{ marginTop: "1rem" }}>
          <label>当前数据源</label>
          <div className="form-row">
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
            <input
              placeholder="编辑名称"
              value={editDsName}
              onChange={(e) => setEditDsName(e.target.value)}
              disabled={!selectedDs}
              style={{ marginLeft: "0.5rem" }}
            />
            <button
              className="btn btn-sm"
              onClick={handleUpdateDatasourceName}
              disabled={
                !selectedDs ||
                !editDsName.trim() ||
                editDsName.trim() === selectedDatasource?.name
              }
              style={{ marginLeft: "0.5rem" }}
            >
              保存名称
            </button>
            <button
              className="btn btn-sm"
              onClick={handleDeleteDatasource}
              disabled={!selectedDs}
              style={{ marginLeft: "0.5rem" }}
            >
              删除数据源
            </button>
            <button
              className="btn"
              onClick={() => setSyncModalOpen(true)}
              disabled={!selectedDs}
              style={{ marginLeft: "0.5rem" }}
            >
              扫描并同步表
            </button>
            <button
              className="btn"
              onClick={() => selectedDs && indexDatasource({ variables: { datasourceId: selectedDs } })}
              disabled={!selectedDs || indexing}
              style={{ marginLeft: "0.5rem" }}
            >
              {indexing ? "索引中..." : "重建全量 RAG 索引"}
            </button>
          </div>
          {selectedDs && selectedDatasource && (
            <div
              style={{
                marginTop: "1rem",
                padding: "0.75rem 1rem",
                background: "#1e293b",
                borderRadius: "6px",
                fontSize: "0.875rem",
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
                gap: "0.5rem 1.5rem",
              }}
            >
              {parsedConnection ? (
                <>
                  <div>
                    <span style={{ color: "#94a3b8" }}>连接 </span>
                    <span>{parsedConnection.connection}</span>
                  </div>
                  <div>
                    <span style={{ color: "#94a3b8" }}>用户名 </span>
                    <span>{parsedConnection.username}</span>
                  </div>
                  <div>
                    <span style={{ color: "#94a3b8" }}>库 </span>
                    <span>{parsedConnection.database}</span>
                  </div>
                </>
              ) : (
                <div style={{ color: "#fca5a5" }}>无法解析连接 URL</div>
              )}
            </div>
          )}
        </div>
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

      <SyncTablesModal
        open={syncModalOpen}
        datasourceId={selectedDs}
        onClose={() => setSyncModalOpen(false)}
        onSynced={() => {
          refetchTables();
          refetchFks();
        }}
      />
    </div>
  );
}
