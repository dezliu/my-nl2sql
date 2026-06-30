"use client";

import { gql, useMutation, useQuery } from "@apollo/client";
import { useState } from "react";

const ALERTS = gql`
  query Alerts($resolved: Boolean) {
    ragAlerts(resolved: $resolved) {
      id
      chunkId
      question
      score
      isResolved
    }
  }
`;

const RESOLVE_ALERT = gql`
  mutation ResolveAlert($alertId: Int!) {
    resolveAlert(alertId: $alertId)
  }
`;

export default function AlertsPage() {
  const [showResolved, setShowResolved] = useState(false);
  const { data, refetch } = useQuery(ALERTS, {
    variables: { resolved: showResolved ? true : false },
    pollInterval: 10000,
  });
  const [resolveAlert] = useMutation(RESOLVE_ALERT);

  const alerts = data?.ragAlerts || [];

  const handleResolve = async (alertId: number) => {
    await resolveAlert({ variables: { alertId } });
    refetch();
  };

  return (
    <div>
      <h1 className="page-title">RAG 告警</h1>

      <div className="card" style={{ marginBottom: "1rem" }}>
        <label style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <input
            type="checkbox"
            checked={showResolved}
            onChange={(e) => setShowResolved(e.target.checked)}
          />
          显示已处理告警
        </label>
      </div>

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Chunk ID</th>
              <th>问题</th>
              <th>评分</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {alerts.map((a: {
              id: number;
              chunkId: number;
              question: string;
              score: number;
              isResolved: boolean;
            }) => (
              <tr key={a.id}>
                <td>{a.id}</td>
                <td>{a.chunkId}</td>
                <td style={{ maxWidth: 300 }}>{a.question.slice(0, 100)}</td>
                <td className={a.score < 0.6 ? "alert-low" : ""}>{a.score.toFixed(2)}</td>
                <td>
                  <span className={`badge ${a.isResolved ? "badge-inactive" : "badge-active"}`}>
                    {a.isResolved ? "已处理" : "待处理"}
                  </span>
                </td>
                <td>
                  {!a.isResolved && (
                    <button className="btn btn-sm btn-success" onClick={() => handleResolve(a.id)}>
                      标记已处理
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {alerts.length === 0 && (
              <tr>
                <td colSpan={6} style={{ textAlign: "center", color: "#9ca3af" }}>
                  暂无告警
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
