"use client";

import { gql, useLazyQuery, useMutation } from "@apollo/client";
import { useCallback, useEffect, useState } from "react";

import { AdminErrorBanner } from "./AdminErrorBanner";
import { AdminModal } from "./AdminModal";
import { formatMutationError } from "../lib/mutation-error";

const SCAN_TABLES = gql`
  query ScanDatasourceTables($datasourceId: Int!) {
    scanDatasourceTables(datasourceId: $datasourceId) {
      tableName
      tableComment
      columnCount
      alreadyExists
      existingTableId
    }
  }
`;

const SYNC_METADATA = gql`
  mutation SyncDatasourceMetadata($input: SyncDatasourceMetadataInput!) {
    syncDatasourceMetadata(input: $input) {
      tablesAdded
      tablesUpdated
      columnsAdded
      columnsUpdated
      fksSynced
      indexedCount
      orphanColumns
      errors
    }
  }
`;

type ScannedTable = {
  tableName: string;
  tableComment: string | null;
  columnCount: number;
  alreadyExists: boolean;
  existingTableId: number | null;
};

type TableRow = ScannedTable & {
  selected: boolean;
  description: string;
};

export function SyncTablesModal({
  open,
  datasourceId,
  onClose,
  onSynced,
}: {
  open: boolean;
  datasourceId: number | null;
  onClose: () => void;
  onSynced: () => void;
}) {
  const [rows, setRows] = useState<TableRow[]>([]);
  const [syncFks, setSyncFks] = useState(true);
  const [indexToRag, setIndexToRag] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [syncSummary, setSyncSummary] = useState<string | null>(null);

  const [scanTables, { loading: scanning }] = useLazyQuery(SCAN_TABLES, {
    fetchPolicy: "network-only",
  });
  const [syncMetadata, { loading: syncing }] = useMutation(SYNC_METADATA);

  const loadScan = useCallback(async () => {
    if (!datasourceId) return;
    setError(null);
    setSyncSummary(null);
    try {
      const { data } = await scanTables({ variables: { datasourceId } });
      const tables: ScannedTable[] = data?.scanDatasourceTables ?? [];
      setRows(
        tables.map((t) => ({
          ...t,
          selected: !t.alreadyExists,
          description: t.tableComment ?? "",
        }))
      );
    } catch (err) {
      setError(formatMutationError(err));
      setRows([]);
    }
  }, [datasourceId, scanTables]);

  useEffect(() => {
    if (open && datasourceId) {
      loadScan();
    }
    if (!open) {
      setRows([]);
      setError(null);
      setSyncSummary(null);
    }
  }, [open, datasourceId, loadScan]);

  const updateRow = (tableName: string, patch: Partial<TableRow>) => {
    setRows((prev) =>
      prev.map((r) => (r.tableName === tableName ? { ...r, ...patch } : r))
    );
  };

  const setAllSelected = (selected: boolean) => {
    setRows((prev) => prev.map((r) => ({ ...r, selected })));
  };

  const selectNewOnly = () => {
    setRows((prev) => prev.map((r) => ({ ...r, selected: !r.alreadyExists })));
  };

  const handleSync = async () => {
    if (!datasourceId) return;
    const selected = rows.filter((r) => r.selected);
    if (selected.length === 0) {
      setError("请至少选择一张表");
      return;
    }
    setError(null);
    setSyncSummary(null);
    try {
      const { data } = await syncMetadata({
        variables: {
          input: {
            datasourceId,
            tables: selected.map((r) => ({
              tableName: r.tableName,
              description: r.description.trim() || null,
              isAllowed: true,
            })),
            syncFks,
            indexToRag,
          },
        },
      });
      const result = data?.syncDatasourceMetadata;
      if (!result) return;

      const parts = [
        `新增表 ${result.tablesAdded}`,
        `更新表 ${result.tablesUpdated}`,
        `新增列 ${result.columnsAdded}`,
        `同步 FK ${result.fksSynced}`,
      ];
      if (result.indexedCount > 0) {
        parts.push(`RAG 入库 ${result.indexedCount}`);
      }
      setSyncSummary(parts.join("，"));

      if (result.errors?.length) {
        setError(result.errors.join("\n"));
      } else {
        onSynced();
        onClose();
      }
    } catch (err) {
      setError(formatMutationError(err));
    }
  };

  return (
    <AdminModal open={open} title="扫描并同步表" onClose={onClose} width={900}>
      <AdminErrorBanner message={error} onDismiss={() => setError(null)} />

      {scanning ? (
        <p>扫描中…</p>
      ) : rows.length === 0 ? (
        <p>未扫描到表，请检查数据源连接与权限。</p>
      ) : (
        <>
          <div className="form-row" style={{ marginBottom: "0.75rem" }}>
            <button type="button" className="btn btn-sm" onClick={() => setAllSelected(true)}>
              全选
            </button>
            <button type="button" className="btn btn-sm" onClick={selectNewOnly}>
              仅新表
            </button>
            <button type="button" className="btn btn-sm" onClick={() => setAllSelected(false)}>
              取消全选
            </button>
            <button type="button" className="btn btn-sm" onClick={loadScan} disabled={scanning}>
              重新扫描
            </button>
          </div>

          <div style={{ maxHeight: "50vh", overflowY: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th style={{ width: 40 }} />
                  <th>表名</th>
                  <th>列数</th>
                  <th>状态</th>
                  <th>表描述（可编辑）</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.tableName}>
                    <td>
                      <input
                        type="checkbox"
                        checked={row.selected}
                        onChange={(e) =>
                          updateRow(row.tableName, { selected: e.target.checked })
                        }
                      />
                    </td>
                    <td>{row.tableName}</td>
                    <td>{row.columnCount}</td>
                    <td>{row.alreadyExists ? "已存在" : "新表"}</td>
                    <td>
                      <input
                        value={row.description}
                        onChange={(e) =>
                          updateRow(row.tableName, { description: e.target.value })
                        }
                        placeholder="表级描述（同步后可继续在列管理中编辑列描述）"
                        style={{ width: "100%" }}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <div className="form-group" style={{ marginTop: "1rem" }}>
        <label style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <input
            type="checkbox"
            checked={syncFks}
            onChange={(e) => setSyncFks(e.target.checked)}
          />
          同步外键关系
        </label>
        <label style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <input
            type="checkbox"
            checked={indexToRag}
            onChange={(e) => setIndexToRag(e.target.checked)}
          />
          同步后入库 RAG
        </label>
      </div>

      {syncSummary && (
        <p style={{ color: "#86efac", fontSize: "0.875rem", marginTop: "0.5rem" }}>{syncSummary}</p>
      )}

      <div className="form-row" style={{ marginTop: "1rem", justifyContent: "flex-end" }}>
        <button type="button" className="btn btn-sm" onClick={onClose} disabled={syncing}>
          取消
        </button>
        <button
          type="button"
          className="btn btn-success"
          onClick={handleSync}
          disabled={syncing || scanning || rows.length === 0}
        >
          {syncing ? "同步中…" : "同步"}
        </button>
      </div>
    </AdminModal>
  );
}
