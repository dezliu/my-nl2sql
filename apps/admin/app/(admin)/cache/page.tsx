"use client";

import { gql, useQuery } from "@apollo/client";

const CACHE_STATS = gql`
  query CacheStats {
    cacheStats {
      totalHits
      exactHits
      semanticHits
      totalTokensSaved
    }
  }
`;

const CACHE_LOGS = gql`
  query CacheHitLogs($limit: Int!) {
    cacheHitLogs(limit: $limit) {
      id
      sessionId
      hitType
      savedTokens
      similarity
      latencyMs
    }
  }
`;

export default function CachePage() {
  const { data: statsData } = useQuery(CACHE_STATS, { pollInterval: 5000 });
  const { data: logsData } = useQuery(CACHE_LOGS, {
    variables: { limit: 100 },
    pollInterval: 5000,
  });

  const stats = statsData?.cacheStats;
  const logs = logsData?.cacheHitLogs || [];
  const hitRate =
    stats && stats.totalHits > 0
      ? ((stats.exactHits + stats.semanticHits) / stats.totalHits * 100).toFixed(1)
      : "0";

  return (
    <div>
      <h1 className="page-title">缓存监控</h1>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-value">{stats?.totalHits ?? 0}</div>
          <div className="stat-label">总命中次数</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats?.exactHits ?? 0}</div>
          <div className="stat-label">精确命中</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats?.semanticHits ?? 0}</div>
          <div className="stat-label">语义命中</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats?.totalTokensSaved ?? 0}</div>
          <div className="stat-label">节省 Token</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{hitRate}%</div>
          <div className="stat-label">命中率</div>
        </div>
      </div>

      <div className="card">
        <h3 style={{ marginBottom: "1rem" }}>命中明细</h3>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Session</th>
              <th>类型</th>
              <th>节省 Token</th>
              <th>相似度</th>
              <th>延迟 (ms)</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log: {
              id: number;
              sessionId: string | null;
              hitType: string;
              savedTokens: number;
              similarity: number | null;
              latencyMs: number;
            }) => (
              <tr key={log.id}>
                <td>{log.id}</td>
                <td>{log.sessionId?.slice(0, 8) ?? "-"}</td>
                <td>{log.hitType}</td>
                <td>{log.savedTokens}</td>
                <td>{log.similarity?.toFixed(3) ?? "-"}</td>
                <td>{log.latencyMs}</td>
              </tr>
            ))}
            {logs.length === 0 && (
              <tr>
                <td colSpan={6} style={{ textAlign: "center", color: "#9ca3af" }}>
                  暂无缓存命中记录
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
