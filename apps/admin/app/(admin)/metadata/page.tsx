"use client";

import { gql, useMutation, useQuery } from "@apollo/client";
import { useState } from "react";

const DATASOURCES = gql`
  query Datasources {
    datasources {
      id
      name
      isActive
    }
  }
`;

const TABLES = gql`
  query Tables($datasourceId: Int!) {
    tables(datasourceId: $datasourceId) {
      id
      tableName
      description
      isAllowed
    }
  }
`;

const INDEX_DATASOURCE = gql`
  mutation IndexDatasource($datasourceId: Int!) {
    indexDatasource(datasourceId: $datasourceId)
  }
`;

export default function MetadataPage() {
  const [selectedDs, setSelectedDs] = useState<number | null>(null);
  const { data: dsData } = useQuery(DATASOURCES);
  const { data: tablesData, refetch } = useQuery(TABLES, {
    variables: { datasourceId: selectedDs },
    skip: !selectedDs,
  });
  const [indexDatasource, { loading: indexing }] = useMutation(INDEX_DATASOURCE);

  const datasources = dsData?.datasources || [];
  const tables = tablesData?.tables || [];

  const handleIndex = async () => {
    if (!selectedDs) return;
    await indexDatasource({ variables: { datasourceId: selectedDs } });
    alert("索引任务已完成");
    refetch();
  };

  return (
    <div>
      <h1 className="page-title">元数据管理</h1>

      <div className="card">
        <div className="form-group">
          <label>数据源</label>
          <select
            value={selectedDs ?? ""}
            onChange={(e) => setSelectedDs(Number(e.target.value))}
          >
            <option value="">选择数据源</option>
            {datasources.map((ds: { id: number; name: string }) => (
              <option key={ds.id} value={ds.id}>
                {ds.name}
              </option>
            ))}
          </select>
        </div>
        <button className="btn" onClick={handleIndex} disabled={!selectedDs || indexing}>
          {indexing ? "索引中..." : "重建 RAG 索引"}
        </button>
      </div>

      {tables.length > 0 && (
        <div className="card">
          <h3 style={{ marginBottom: "1rem" }}>表列表</h3>
          <table>
            <thead>
              <tr>
                <th>表名</th>
                <th>描述</th>
                <th>允许查询</th>
              </tr>
            </thead>
            <tbody>
              {tables.map((t: { id: number; tableName: string; description: string; isAllowed: boolean }) => (
                <tr key={t.id}>
                  <td>{t.tableName}</td>
                  <td>{t.description || "-"}</td>
                  <td>{t.isAllowed ? "是" : "否"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
