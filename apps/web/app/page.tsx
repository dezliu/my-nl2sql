"use client";

import { gql, useQuery } from "@apollo/client";
import { useCallback, useRef, useState } from "react";

import { askStream, type SseEvent } from "../lib/sse";

const DATASOURCES_QUERY = gql`
  query Datasources {
    datasources {
      id
      name
      isActive
    }
  }
`;

type StreamEvent = SseEvent;

function ResultTable({ data }: { data: Record<string, unknown> }) {
  const columns = (data.columns as string[]) || [];
  const rows = (data.rows as Record<string, unknown>[]) || [];
  if (!columns.length) return <pre>{JSON.stringify(data, null, 2)}</pre>;
  return (
    <table className="result-table">
      <thead>
        <tr>
          {columns.map((c) => (
            <th key={c}>{c}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, i) => (
          <tr key={i}>
            {columns.map((c) => (
              <td key={c}>{String(row[c] ?? "")}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function StreamingText({ role, text, active }: { role: string; text: string; active: boolean }) {
  return (
    <div className={`event-card ${role}`}>
      <div className="event-label">{role.toUpperCase()}</div>
      <div className="event-content">
        {text}
        {active && <span className="typing-cursor">▋</span>}
      </div>
    </div>
  );
}

function EventCard({ event }: { event: StreamEvent }) {
  const typeClass = event.eventType.toLowerCase().replace("_", "");
  const label = event.eventType;

  let content: React.ReactNode;
  switch (event.eventType) {
    case "INTENT":
      content = <span>意图: {String(event.data.intent)}</span>;
      break;
    case "RAG_CHUNK":
      content = (
        <div>
          检索到 {String(event.data.count)} 条相关片段
          {(event.data.chunks as { content: string; score: number }[])?.map((c, i) => (
            <div key={i} style={{ marginTop: "0.5rem", opacity: 0.8 }}>
              [{c.score?.toFixed(3)}] {c.content?.slice(0, 200)}...
            </div>
          ))}
        </div>
      );
      break;
    case "LLM_TOKEN":
      return null;
    case "THOUGHT":
      content = <span>{String(event.data.text)}</span>;
      break;
    case "SQL":
      content = <code>{String(event.data.sql)}</code>;
      break;
    case "RESULT":
      content = <ResultTable data={event.data} />;
      break;
    case "SUMMARY":
      content = <span>{String(event.data.text)}</span>;
      break;
    case "ERROR":
      content = <span style={{ color: "#ef4444" }}>{String(event.data.message)}</span>;
      break;
    case "DONE":
      return null;
    default:
      content = <pre>{JSON.stringify(event.data, null, 2)}</pre>;
  }

  return (
    <div className={`event-card ${typeClass}`}>
      <div className="event-label">{label}</div>
      <div className="event-content">{content}</div>
    </div>
  );
}

export default function HomePage() {
  const [question, setQuestion] = useState("");
  const [deepThink, setDeepThink] = useState(false);
  const [executionMode, setExecutionMode] = useState("AUTO");
  const [datasourceId, setDatasourceId] = useState<number | null>(null);
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [streaming, setStreaming] = useState<Record<string, { text: string; active: boolean }>>({});
  const [loading, setLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const { data: dsData } = useQuery(DATASOURCES_QUERY);

  const handleSubmit = useCallback(async () => {
    if (!question.trim() || !datasourceId) return;

    abortRef.current?.abort();
    abortRef.current = new AbortController();

    setEvents([]);
    setStreaming({});
    setLoading(true);

    try {
      await askStream(
        {
          question,
          datasourceId,
          deepThink,
          executionMode,
        },
        (evt) => {
          if (evt.eventType === "LLM_TOKEN") {
            const role = String(evt.data.role || "summary");
            const delta = String(evt.data.delta || "");
            setStreaming((prev) => {
              const current = prev[role]?.text ?? "";
              return {
                ...prev,
                [role]: { text: current + delta, active: !evt.data.done },
              };
            });
            return;
          }

          if (evt.eventType === "SUMMARY" || evt.eventType === "SQL") {
            const role = evt.eventType === "SQL" ? "sql" : "summary";
            setStreaming((prev) => ({
              ...prev,
              [role]: { text: String(evt.data.text ?? evt.data.sql ?? ""), active: false },
            }));
          }

          setEvents((prev) => [...prev, evt]);

          if (evt.eventType === "DONE") {
            setLoading(false);
            setStreaming((prev) => {
              const next = { ...prev };
              for (const key of Object.keys(next)) {
                next[key] = { ...next[key], active: false };
              }
              return next;
            });
          }
        },
        abortRef.current.signal
      );
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setEvents((prev) => [
          ...prev,
          { eventType: "ERROR", data: { message: String(err) } },
        ]);
      }
    } finally {
      setLoading(false);
      setStreaming((prev) => {
        const next = { ...prev };
        for (const key of Object.keys(next)) {
          next[key] = { ...next[key], active: false };
        }
        return next;
      });
    }
  }, [question, datasourceId, deepThink, executionMode]);

  const datasources = dsData?.datasources || [];

  return (
    <div className="container">
      <div className="header">
        <h1>NL2SQL</h1>
        <p>用自然语言查询数据库</p>
      </div>

      <div className="input-area">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="例如：查询每个用户的订单总数"
        />
        <div className="controls">
          <label>
            <input
              type="checkbox"
              checked={deepThink}
              onChange={(e) => setDeepThink(e.target.checked)}
            />
            深度思考 (ReAct)
          </label>
          <select
            value={executionMode}
            onChange={(e) => setExecutionMode(e.target.value)}
          >
            <option value="AUTO">自动执行</option>
            <option value="GENERATE_ONLY">仅生成 SQL</option>
            <option value="EXECUTE">强制执行</option>
          </select>
          <select
            value={datasourceId ?? ""}
            onChange={(e) => setDatasourceId(Number(e.target.value))}
          >
            <option value="">选择数据源</option>
            {datasources.map((ds: { id: number; name: string }) => (
              <option key={ds.id} value={ds.id}>
                {ds.name}
              </option>
            ))}
          </select>
          <button className="btn-primary" onClick={handleSubmit} disabled={loading}>
            {loading ? "处理中..." : "提问"}
          </button>
        </div>
      </div>

      <div className="stream-area">
        {Object.entries(streaming).map(([role, { text, active }]) =>
          text ? (
            <StreamingText key={role} role={role} text={text} active={active} />
          ) : null
        )}
        {events.map((evt, i) => (
          <EventCard key={i} event={evt} />
        ))}
      </div>
    </div>
  );
}
