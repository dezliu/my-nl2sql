"use client";

import { gql, useMutation, useQuery } from "@apollo/client";
import { FormEvent, useEffect, useState } from "react";

const SQL_ROW_LIMIT = gql`
  query SqlRowLimit {
    sqlRowLimit
  }
`;

const UPDATE_SQL_ROW_LIMIT = gql`
  mutation UpdateSqlRowLimit($limit: Int!) {
    updateSqlRowLimit(limit: $limit)
  }
`;

export default function SettingsPage() {
  const { data, loading, refetch } = useQuery(SQL_ROW_LIMIT);
  const [updateLimit, { loading: saving }] = useMutation(UPDATE_SQL_ROW_LIMIT);
  const [limit, setLimit] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (data?.sqlRowLimit != null) {
      setLimit(String(data.sqlRowLimit));
    }
  }, [data?.sqlRowLimit]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setMessage(null);
    setError(null);
    const value = parseInt(limit, 10);
    if (!Number.isFinite(value) || value <= 0) {
      setError("请输入大于 0 的整数");
      return;
    }
    try {
      await updateLimit({ variables: { limit: value } });
      await refetch();
      setMessage("已保存");
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    }
  }

  return (
    <div>
      <h1 className="page-title">系统设置</h1>

      <div className="card" style={{ maxWidth: 480 }}>
        <h3 style={{ marginBottom: "0.5rem" }}>SQL 返回行数限制</h3>
        <p style={{ marginBottom: "1rem", color: "var(--muted)", fontSize: "0.9rem" }}>
          当 LLM 生成的查询可能返回多条记录时，Prompt 会要求其必须加上{" "}
          <code>LIMIT N</code>；校验阶段也会对未带 LIMIT 的 SQL 自动追加该上限。
        </p>

        {loading ? (
          <p>加载中…</p>
        ) : (
          <form onSubmit={handleSubmit}>
            <label style={{ display: "block", marginBottom: "0.5rem" }}>
              最大行数 N
            </label>
            <input
              type="number"
              min={1}
              value={limit}
              onChange={(e) => setLimit(e.target.value)}
              style={{ width: "100%", marginBottom: "1rem" }}
            />
            <button type="submit" disabled={saving}>
              {saving ? "保存中…" : "保存"}
            </button>
            {message && (
              <p style={{ marginTop: "0.75rem", color: "var(--success, #16a34a)" }}>
                {message}
              </p>
            )}
            {error && (
              <p style={{ marginTop: "0.75rem", color: "var(--danger, #dc2626)" }}>
                {error}
              </p>
            )}
          </form>
        )}
      </div>
    </div>
  );
}
