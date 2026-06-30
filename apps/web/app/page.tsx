"use client";

import { gql, useQuery } from "@apollo/client";
import { useCallback, useEffect, useRef, useState } from "react";

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

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  streaming: boolean;
  phase?: string;
  sql?: string;
  result?: Record<string, unknown>;
  error?: string;
};

const PHASE_HINT: Record<string, string> = {
  connected: "已连接",
  load_context: "加载上下文",
  intent_classifier: "识别意图",
  rag_router: "路由判断",
  hybrid_retrieve: "知识检索",
  retrieval_judge: "评估检索",
  query_expander: "查询扩展",
  sql_generate: "生成 SQL",
  sql_safety: "SQL 校验",
  execute_or_return: "执行查询",
  result_summarizer: "生成总结",
  direct_llm: "生成回答",
  direct_reply: "直接回复",
};

function ResultTable({ data }: { data: Record<string, unknown> }) {
  const columns = (data.columns as string[]) || [];
  const rows = (data.rows as Record<string, unknown>[]) || [];
  if (!columns.length) return <pre className="result-raw">{JSON.stringify(data, null, 2)}</pre>;
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

function ChatBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  return (
    <div className={`chat-row ${isUser ? "chat-row-user" : "chat-row-assistant"}`}>
      <div className={`chat-avatar ${isUser ? "avatar-user" : "avatar-assistant"}`}>
        {isUser ? "你" : "AI"}
      </div>
      <div className={`chat-bubble ${isUser ? "bubble-user" : "bubble-assistant"}`}>
        {!isUser && message.phase && message.streaming && (
          <div className="chat-phase">{message.phase}</div>
        )}
        {message.content ? (
          <div className="chat-content">
            {message.content}
            {message.streaming && <span className="typing-cursor">▋</span>}
          </div>
        ) : message.streaming ? (
          <div className="chat-typing">
            <span className="dot" />
            <span className="dot" />
            <span className="dot" />
          </div>
        ) : null}
        {message.sql && (
          <pre className="chat-sql">
            <span className="chat-sql-label">SQL</span>
            {message.sql}
          </pre>
        )}
        {message.result && <ResultTable data={message.result} />}
        {message.error && <div className="chat-error">{message.error}</div>}
      </div>
    </div>
  );
}

export default function HomePage() {
  const [question, setQuestion] = useState("");
  const [deepThink, setDeepThink] = useState(false);
  const [executionMode, setExecutionMode] = useState("AUTO");
  const [datasourceId, setDatasourceId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const assistantIdRef = useRef<string | null>(null);
  const streamBuffersRef = useRef<Record<string, string>>({});

  const { data: dsData } = useQuery(DATASOURCES_QUERY);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const updateAssistant = useCallback((patch: Partial<ChatMessage>) => {
    const id = assistantIdRef.current;
    if (!id) return;
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, ...patch } : m))
    );
  }, []);

  const handleStreamEvent = useCallback(
    (evt: SseEvent) => {
      switch (evt.eventType) {
        case "STATUS": {
          const phase = String(evt.data.phase ?? "");
          const msg = String(evt.data.message ?? PHASE_HINT[phase] ?? "处理中…");
          updateAssistant({ phase: msg, streaming: true });
          break;
        }
        case "INTENT":
          updateAssistant({
            phase: `意图：${String(evt.data.intent)}`,
            streaming: true,
          });
          break;
        case "RAG_CHUNK":
          updateAssistant({
            phase: `检索到 ${String(evt.data.count)} 条相关片段`,
            streaming: true,
          });
          break;
        case "LLM_TOKEN": {
          const role = String(evt.data.role || "summary");
          const delta = String(evt.data.delta || "");
          const buffers = streamBuffersRef.current;
          buffers[role] = (buffers[role] || "") + delta;
          const combined = Object.values(buffers).join("\n\n");
          updateAssistant({
            content: combined,
            streaming: true,
            phase: role === "sql" ? "正在生成 SQL…" : role === "thought" ? "深度思考中…" : "正在生成回答…",
          });
          break;
        }
        case "SQL":
          updateAssistant({
            sql: String(evt.data.sql ?? ""),
            phase: "SQL 已生成",
            streaming: true,
          });
          break;
        case "RESULT":
          updateAssistant({
            result: evt.data,
            phase: "查询完成",
            streaming: true,
          });
          break;
        case "SUMMARY": {
          const text = String(evt.data.text ?? "");
          if (text) {
            updateAssistant({ content: text, streaming: true, phase: "总结中…" });
          }
          break;
        }
        case "ERROR": {
          const errs = Array.isArray(evt.data.errors) ? evt.data.errors : [];
          const detail = errs.length ? `: ${errs.join("; ")}` : "";
          updateAssistant({
            error: `${String(evt.data.message)}${detail}`,
            streaming: false,
            phase: undefined,
          });
          break;
        }
        case "DONE":
          updateAssistant({ streaming: false, phase: undefined });
          break;
        default:
          break;
      }
    },
    [updateAssistant]
  );

  const handleSubmit = useCallback(async () => {
    if (!question.trim() || !datasourceId || loading) return;

    abortRef.current?.abort();
    abortRef.current = new AbortController();

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: question.trim(),
      streaming: false,
    };
    const assistantId = `assistant-${Date.now()}`;
    assistantIdRef.current = assistantId;
    streamBuffersRef.current = {};

    const assistantMsg: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      streaming: true,
      phase: "正在连接…",
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setLoading(true);

    try {
      await askStream(
        {
          question: question.trim(),
          datasourceId,
          deepThink,
          executionMode,
        },
        handleStreamEvent,
        abortRef.current.signal
      );
      updateAssistant({ streaming: false, phase: undefined });
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        updateAssistant({
          error: String(err),
          streaming: false,
          phase: undefined,
        });
      }
    } finally {
      setLoading(false);
      assistantIdRef.current = null;
    }
  }, [question, datasourceId, deepThink, executionMode, loading, handleStreamEvent, updateAssistant]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const datasources = dsData?.datasources || [];

  return (
    <div className="chat-layout">
      <header className="chat-header">
        <h1>NL2SQL</h1>
        <p>用自然语言查询数据库</p>
      </header>

      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">
            <p>输入问题开始对话，例如：</p>
            <ul>
              <li>查询每个用户的订单总数</li>
              <li>最近 7 天的销售额趋势</li>
            </ul>
          </div>
        )}
        {messages.map((m) => (
          <ChatBubble key={m.id} message={m} />
        ))}
        <div ref={bottomRef} />
      </div>

      <div className="chat-composer">
        <div className="composer-options">
          <label>
            <input
              type="checkbox"
              checked={deepThink}
              onChange={(e) => setDeepThink(e.target.checked)}
              disabled={loading}
            />
            深度思考
          </label>
          <select
            value={executionMode}
            onChange={(e) => setExecutionMode(e.target.value)}
            disabled={loading}
          >
            <option value="AUTO">自动执行</option>
            <option value="GENERATE_ONLY">仅生成 SQL</option>
            <option value="EXECUTE">强制执行</option>
          </select>
          <select
            value={datasourceId ?? ""}
            onChange={(e) => setDatasourceId(Number(e.target.value))}
            disabled={loading}
          >
            <option value="">选择数据源</option>
            {datasources.map((ds: { id: number; name: string }) => (
              <option key={ds.id} value={ds.id}>
                {ds.name}
              </option>
            ))}
          </select>
        </div>
        <div className="composer-input-row">
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入问题，Enter 发送，Shift+Enter 换行"
            disabled={loading}
            rows={2}
          />
          <button
            className="btn-send"
            onClick={handleSubmit}
            disabled={loading || !question.trim() || !datasourceId}
          >
            {loading ? "…" : "发送"}
          </button>
        </div>
      </div>
    </div>
  );
}
