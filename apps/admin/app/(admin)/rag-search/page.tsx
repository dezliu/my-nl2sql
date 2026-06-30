"use client";

import { gql, useLazyQuery, useQuery } from "@apollo/client";
import { useState } from "react";

const DATASOURCES = gql`
  query Datasources {
    datasources {
      id
      name
    }
  }
`;

const RAG_SEARCH = gql`
  query TestRagSearch($query: String!, $datasourceId: Int, $topK: Int) {
    testRagSearch(query: $query, datasourceId: $datasourceId, topK: $topK) {
      chunkId
      content
      score
      docType
    }
  }
`;

export default function RagSearchPage() {
  const [query, setQuery] = useState("");
  const [datasourceId, setDatasourceId] = useState<number | null>(null);
  const [topK, setTopK] = useState(5);

  const { data: dsData } = useQuery(DATASOURCES);
  const [search, { data: searchData, loading }] = useLazyQuery(RAG_SEARCH);

  const datasources = dsData?.datasources || [];
  const results = searchData?.testRagSearch || [];

  const handleSearch = () => {
    if (!query.trim()) return;
    search({
      variables: {
        query,
        datasourceId,
        topK,
      },
    });
  };

  return (
    <div>
      <h1 className="page-title">向量检索测试</h1>

      <div className="card">
        <div className="form-group">
          <label>查询文本</label>
          <textarea value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        <div className="form-row">
          <select
            value={datasourceId ?? ""}
            onChange={(e) => setDatasourceId(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">全部数据源</option>
            {datasources.map((ds: { id: number; name: string }) => (
              <option key={ds.id} value={ds.id}>
                {ds.name}
              </option>
            ))}
          </select>
          <input
            type="number"
            min={1}
            max={20}
            value={topK}
            onChange={(e) => setTopK(Number(e.target.value))}
            style={{ width: 80 }}
          />
          <button className="btn" onClick={handleSearch} disabled={loading}>
            {loading ? "检索中..." : "检索"}
          </button>
        </div>
      </div>

      {results.length > 0 && (
        <div className="card">
          <h3>结果 ({results.length})</h3>
          {results.map(
            (r: { chunkId: string; content: string; score: number; docType: string }, i: number) => (
              <div key={i} className="search-result">
                <div className="search-meta">
                  [{r.docType}] score={r.score.toFixed(4)} chunk={r.chunkId}
                </div>
                <pre>{r.content}</pre>
              </div>
            )
          )}
        </div>
      )}
    </div>
  );
}
