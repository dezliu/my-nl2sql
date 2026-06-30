"use client";

import { gql, useLazyQuery, useMutation, useQuery } from "@apollo/client";
import { useState } from "react";

import { AdminErrorBanner } from "../../../components/AdminErrorBanner";
import { formatMutationError } from "../../../lib/mutation-error";

const DATASOURCES = gql`
  query Datasources {
    datasources {
      id
      name
    }
  }
`;

const EVAL_CASES = gql`
  query RagEvalCases {
    ragEvalCases {
      id
      question
      datasourceId
      expectedChunkIds
      expectedTables
      enabled
      note
    }
  }
`;

const EVAL_RUNS = gql`
  query RagEvalRuns {
    ragEvalRuns(limit: 20) {
      id
      topK
      datasourceId
      caseCount
      recallAtK
      mrr
      status
      createdAt
    }
  }
`;

const EVAL_RUN_DETAIL = gql`
  query RagEvalRun($runId: Int!) {
    ragEvalRun(runId: $runId) {
      id
      topK
      datasourceId
      caseCount
      recallAtK
      mrr
      status
      errorMessage
      createdAt
      items {
        id
        caseId
        question
        recall
        mrr
        matchMode
        retrievedChunkIds
        hitChunkIds
        skipped
        skipReason
      }
    }
  }
`;

const CREATE_CASE = gql`
  mutation CreateRagEvalCase($input: CreateRagEvalCaseInput!) {
    createRagEvalCase(input: $input) {
      id
    }
  }
`;

const UPDATE_CASE = gql`
  mutation UpdateRagEvalCase($input: UpdateRagEvalCaseInput!) {
    updateRagEvalCase(input: $input) {
      id
    }
  }
`;

const DELETE_CASE = gql`
  mutation DeleteRagEvalCase($caseId: Int!) {
    deleteRagEvalCase(caseId: $caseId)
  }
`;

const IMPORT_BENCHMARK = gql`
  mutation ImportRagEvalBenchmark {
    importRagEvalBenchmark {
      importedCount
      skippedCount
    }
  }
`;

const RUN_EVAL = gql`
  mutation RunRagEval($topK: Int!, $datasourceId: Int) {
    runRagEval(topK: $topK, datasourceId: $datasourceId) {
      runId
      caseCount
      evaluatedCount
      skippedCount
      recallAtK
      mrr
    }
  }
`;

type EvalCase = {
  id: number;
  question: string;
  datasourceId: number | null;
  expectedChunkIds: number[] | null;
  expectedTables: string[] | null;
  enabled: boolean;
  note: string | null;
};

type EvalRunSummary = {
  id: number;
  topK: number;
  datasourceId: number | null;
  caseCount: number;
  recallAtK: number | null;
  mrr: number | null;
  status: string;
  createdAt: string;
};

function parseCsvList(value: string): string[] {
  return value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function parseIntList(value: string): number[] {
  return value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => Number(s))
    .filter((n) => !Number.isNaN(n));
}

function formatPct(value: number | null | undefined): string {
  if (value == null) return "-";
  return `${(value * 100).toFixed(1)}%`;
}

export default function RagEvalPage() {
  const [error, setError] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [runDatasourceId, setRunDatasourceId] = useState<number | null>(null);
  const [topK, setTopK] = useState(5);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [newCase, setNewCase] = useState({
    question: "",
    datasourceId: "" as string | number,
    expectedTables: "",
    expectedChunkIds: "",
    note: "",
    enabled: true,
  });
  const [editForm, setEditForm] = useState({
    question: "",
    datasourceId: "" as string | number,
    expectedTables: "",
    expectedChunkIds: "",
    note: "",
    enabled: true,
  });

  const { data: dsData } = useQuery(DATASOURCES);
  const { data: casesData, refetch: refetchCases } = useQuery(EVAL_CASES);
  const { data: runsData, refetch: refetchRuns } = useQuery(EVAL_RUNS);
  const [loadRunDetail, { data: runDetailData, loading: runDetailLoading }] =
    useLazyQuery(EVAL_RUN_DETAIL);

  const [createCase] = useMutation(CREATE_CASE);
  const [updateCase] = useMutation(UPDATE_CASE);
  const [deleteCase] = useMutation(DELETE_CASE);
  const [importBenchmark, { loading: importing }] = useMutation(IMPORT_BENCHMARK);
  const [runEval, { loading: running }] = useMutation(RUN_EVAL);

  const datasources = dsData?.datasources || [];
  const cases: EvalCase[] = casesData?.ragEvalCases || [];
  const runs: EvalRunSummary[] = runsData?.ragEvalRuns || [];
  const runDetail = runDetailData?.ragEvalRun;

  const startEdit = (c: EvalCase) => {
    setEditingId(c.id);
    setEditForm({
      question: c.question,
      datasourceId: c.datasourceId ?? "",
      expectedTables: (c.expectedTables || []).join(", "),
      expectedChunkIds: (c.expectedChunkIds || []).join(", "),
      note: c.note || "",
      enabled: c.enabled,
    });
  };

  const handleCreate = async () => {
    if (!newCase.question.trim()) return;
    try {
      setError(null);
      const tables = parseCsvList(newCase.expectedTables);
      const chunkIds = parseIntList(newCase.expectedChunkIds);
      await createCase({
        variables: {
          input: {
            question: newCase.question.trim(),
            datasourceId: newCase.datasourceId ? Number(newCase.datasourceId) : null,
            expectedTables: tables.length ? tables : null,
            expectedChunkIds: chunkIds.length ? chunkIds : null,
            enabled: newCase.enabled,
            note: newCase.note || null,
          },
        },
      });
      setNewCase({
        question: "",
        datasourceId: "",
        expectedTables: "",
        expectedChunkIds: "",
        note: "",
        enabled: true,
      });
      refetchCases();
    } catch (err) {
      setError(formatMutationError(err));
    }
  };

  const handleUpdate = async () => {
    if (editingId == null) return;
    try {
      setError(null);
      const tables = parseCsvList(editForm.expectedTables);
      const chunkIds = parseIntList(editForm.expectedChunkIds);
      await updateCase({
        variables: {
          input: {
            id: editingId,
            question: editForm.question.trim(),
            datasourceId: editForm.datasourceId ? Number(editForm.datasourceId) : null,
            expectedTables: tables,
            expectedChunkIds: chunkIds,
            enabled: editForm.enabled,
            note: editForm.note || null,
          },
        },
      });
      setEditingId(null);
      refetchCases();
    } catch (err) {
      setError(formatMutationError(err));
    }
  };

  const handleRunEval = async () => {
    try {
      setError(null);
      const result = await runEval({
        variables: {
          topK,
          datasourceId: runDatasourceId,
        },
      });
      const runId = result.data?.runRagEval?.runId;
      await refetchRuns();
      if (runId) {
        setSelectedRunId(runId);
        loadRunDetail({ variables: { runId } });
      }
    } catch (err) {
      setError(formatMutationError(err));
    }
  };

  const selectRun = (runId: number) => {
    setSelectedRunId(runId);
    loadRunDetail({ variables: { runId } });
  };

  return (
    <div>
      <h1 className="page-title">离线评估</h1>
      <p style={{ color: "#666", marginBottom: "1rem" }}>
        基于金标测试集批量评估混合检索，指标为 Recall@K 与 MRR。评估前请确保相关元数据已入库索引。
      </p>
      <AdminErrorBanner message={error} onDismiss={() => setError(null)} />

      <div className="card">
        <h3>运行评估</h3>
        <div className="form-row">
          <select
            value={runDatasourceId ?? ""}
            onChange={(e) =>
              setRunDatasourceId(e.target.value ? Number(e.target.value) : null)
            }
          >
            <option value="">全部数据源</option>
            {datasources.map((ds: { id: number; name: string }) => (
              <option key={ds.id} value={ds.id}>
                {ds.name}
              </option>
            ))}
          </select>
          <label>
            Top K
            <input
              type="number"
              min={1}
              max={50}
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
              style={{ width: 72, marginLeft: 8 }}
            />
          </label>
          <button className="btn" onClick={handleRunEval} disabled={running || cases.length === 0}>
            {running ? "评估中..." : "开始评估"}
          </button>
          <span style={{ color: "#888" }}>已启用用例：{cases.filter((c) => c.enabled).length}</span>
        </div>
      </div>

      <div className="card">
        <h3>测试用例</h3>
        <div className="form-row" style={{ marginBottom: "1rem" }}>
          <button
            className="btn btn-sm"
            disabled={importing}
            onClick={async () => {
              try {
                setError(null);
                const res = await importBenchmark();
                const imp = res.data?.importRagEvalBenchmark;
                alert(`导入完成：新增 ${imp?.importedCount ?? 0} 条，跳过 ${imp?.skippedCount ?? 0} 条`);
                refetchCases();
              } catch (err) {
                setError(formatMutationError(err));
              }
            }}
          >
            {importing ? "导入中..." : "从 JSON 导入基准集"}
          </button>
        </div>

        <div className="form-group">
          <label>新增用例</label>
          <textarea
            placeholder="问题"
            value={newCase.question}
            onChange={(e) => setNewCase({ ...newCase, question: e.target.value })}
          />
        </div>
        <div className="form-row">
          <select
            value={newCase.datasourceId}
            onChange={(e) => setNewCase({ ...newCase, datasourceId: e.target.value })}
          >
            <option value="">全部数据源</option>
            {datasources.map((ds: { id: number; name: string }) => (
              <option key={ds.id} value={ds.id}>
                {ds.name}
              </option>
            ))}
          </select>
          <input
            placeholder="期望表名（逗号分隔）"
            value={newCase.expectedTables}
            onChange={(e) => setNewCase({ ...newCase, expectedTables: e.target.value })}
          />
          <input
            placeholder="期望 chunk_id（逗号分隔）"
            value={newCase.expectedChunkIds}
            onChange={(e) => setNewCase({ ...newCase, expectedChunkIds: e.target.value })}
          />
          <button className="btn" onClick={handleCreate}>
            添加
          </button>
        </div>

        <table>
          <thead>
            <tr>
              <th>问题</th>
              <th>数据源</th>
              <th>期望表</th>
              <th>期望 chunk</th>
              <th>启用</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {cases.map((c) =>
              editingId === c.id ? (
                <tr key={c.id}>
                  <td colSpan={6}>
                    <div className="form-group">
                      <textarea
                        value={editForm.question}
                        onChange={(e) => setEditForm({ ...editForm, question: e.target.value })}
                      />
                    </div>
                    <div className="form-row">
                      <select
                        value={editForm.datasourceId}
                        onChange={(e) =>
                          setEditForm({ ...editForm, datasourceId: e.target.value })
                        }
                      >
                        <option value="">全部数据源</option>
                        {datasources.map((ds: { id: number; name: string }) => (
                          <option key={ds.id} value={ds.id}>
                            {ds.name}
                          </option>
                        ))}
                      </select>
                      <input
                        value={editForm.expectedTables}
                        onChange={(e) =>
                          setEditForm({ ...editForm, expectedTables: e.target.value })
                        }
                        placeholder="期望表名"
                      />
                      <input
                        value={editForm.expectedChunkIds}
                        onChange={(e) =>
                          setEditForm({ ...editForm, expectedChunkIds: e.target.value })
                        }
                        placeholder="期望 chunk_id"
                      />
                      <label>
                        <input
                          type="checkbox"
                          checked={editForm.enabled}
                          onChange={(e) =>
                            setEditForm({ ...editForm, enabled: e.target.checked })
                          }
                        />{" "}
                        启用
                      </label>
                      <button className="btn btn-sm" onClick={handleUpdate}>
                        保存
                      </button>
                      <button className="btn btn-sm" onClick={() => setEditingId(null)}>
                        取消
                      </button>
                    </div>
                  </td>
                </tr>
              ) : (
                <tr key={c.id}>
                  <td>{c.question}</td>
                  <td>{c.datasourceId ?? "全部"}</td>
                  <td>{(c.expectedTables || []).join(", ") || "-"}</td>
                  <td>{(c.expectedChunkIds || []).join(", ") || "-"}</td>
                  <td>{c.enabled ? "是" : "否"}</td>
                  <td>
                    <button className="btn btn-sm" onClick={() => startEdit(c)}>
                      编辑
                    </button>
                    <button
                      className="btn btn-sm"
                      style={{ marginLeft: "0.5rem" }}
                      onClick={async () => {
                        try {
                          setError(null);
                          await deleteCase({ variables: { caseId: c.id } });
                          refetchCases();
                        } catch (err) {
                          setError(formatMutationError(err));
                        }
                      }}
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

      <div className="card">
        <h3>评估报告</h3>
        <div style={{ display: "flex", gap: "1.5rem", alignItems: "flex-start" }}>
          <div style={{ minWidth: 220 }}>
            <h4>历史运行</h4>
            {runs.length === 0 && <p style={{ color: "#888" }}>暂无记录</p>}
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {runs.map((run) => (
                <li key={run.id} style={{ marginBottom: "0.5rem" }}>
                  <button
                    className={`btn btn-sm${selectedRunId === run.id ? " active" : ""}`}
                    onClick={() => selectRun(run.id)}
                  >
                    #{run.id} · K={run.topK} · {run.status}
                  </button>
                  <div style={{ fontSize: 12, color: "#888" }}>
                    R@{run.topK} {formatPct(run.recallAtK)} · MRR {run.mrr?.toFixed(3) ?? "-"}
                  </div>
                </li>
              ))}
            </ul>
          </div>

          <div style={{ flex: 1 }}>
            {runDetailLoading && <p>加载中...</p>}
            {!runDetailLoading && !runDetail && (
              <p style={{ color: "#888" }}>选择左侧运行记录查看明细</p>
            )}
            {runDetail && (
              <>
                <div className="form-row" style={{ marginBottom: "1rem" }}>
                  <div className="card" style={{ padding: "0.75rem 1rem", margin: 0 }}>
                    <strong>Recall@{runDetail.topK}</strong>
                    <div style={{ fontSize: 24 }}>{formatPct(runDetail.recallAtK)}</div>
                  </div>
                  <div className="card" style={{ padding: "0.75rem 1rem", margin: 0 }}>
                    <strong>MRR</strong>
                    <div style={{ fontSize: 24 }}>{runDetail.mrr?.toFixed(4) ?? "-"}</div>
                  </div>
                  <div className="card" style={{ padding: "0.75rem 1rem", margin: 0 }}>
                    <strong>用例数</strong>
                    <div style={{ fontSize: 24 }}>{runDetail.caseCount}</div>
                  </div>
                </div>
                {runDetail.errorMessage && (
                  <p style={{ color: "crimson" }}>{runDetail.errorMessage}</p>
                )}
                <table>
                  <thead>
                    <tr>
                      <th>问题</th>
                      <th>模式</th>
                      <th>Recall</th>
                      <th>MRR</th>
                      <th>命中 chunk</th>
                      <th>TopK 预览</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runDetail.items.map(
                      (item: {
                        id: number;
                        question: string;
                        matchMode: string;
                        recall: number;
                        mrr: number;
                        hitChunkIds: string[];
                        retrievedChunkIds: string[];
                        skipped: boolean;
                        skipReason: string | null;
                      }) => (
                        <tr key={item.id}>
                          <td>{item.question}</td>
                          <td>{item.skipped ? "跳过" : item.matchMode}</td>
                          <td>{item.skipped ? "-" : formatPct(item.recall)}</td>
                          <td>{item.skipped ? "-" : item.mrr.toFixed(4)}</td>
                          <td>
                            {item.skipped
                              ? item.skipReason || "-"
                              : item.hitChunkIds.join(", ") || "无"}
                          </td>
                          <td style={{ fontSize: 12, maxWidth: 200 }}>
                            {item.retrievedChunkIds.slice(0, topK).join(", ")}
                          </td>
                        </tr>
                      )
                    )}
                  </tbody>
                </table>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
