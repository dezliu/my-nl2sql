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

const ALERTS = gql`
  query Alerts {
    ragAlerts(resolved: false) {
      id
      question
      score
    }
  }
`;

export default function DashboardPage() {
  const { data: cacheData } = useQuery(CACHE_STATS, { pollInterval: 10000 });
  const { data: alertData } = useQuery(ALERTS, { pollInterval: 10000 });

  const stats = cacheData?.cacheStats;
  const alerts = alertData?.ragAlerts || [];

  return (
    <div>
      <h1 className="page-title">系统概览</h1>
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-value">{stats?.totalHits ?? "-"}</div>
          <div className="stat-label">缓存总命中</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats?.exactHits ?? "-"}</div>
          <div className="stat-label">精确命中</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats?.semanticHits ?? "-"}</div>
          <div className="stat-label">语义命中</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats?.totalTokensSaved ?? "-"}</div>
          <div className="stat-label">节省 Token</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{alerts.length}</div>
          <div className="stat-label">未处理告警</div>
        </div>
      </div>
      <div className="card">
        <h3 style={{ marginBottom: "1rem" }}>快速入口</h3>
        <p style={{ color: "#9ca3af" }}>
          使用左侧导航管理 Prompt、元数据、缓存监控和 RAG 告警。
        </p>
      </div>
    </div>
  );
}
