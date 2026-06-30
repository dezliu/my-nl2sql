"use client";

import { gql, useLazyQuery } from "@apollo/client";
import { useEffect, useRef, useState } from "react";

const TABLES_DETAIL = gql`
  query TablesDetail($datasourceId: Int!) {
    tablesDetail(datasourceId: $datasourceId) {
      tableName
    }
  }
`;

type DatasourceOption = { id: number; name: string };

type TableMultiSelectProps = {
  datasourceId: number | null;
  datasources: DatasourceOption[];
  value: string[];
  onChange: (tables: string[]) => void;
  placeholder?: string;
};

export function TableMultiSelect({
  datasourceId,
  datasources,
  value,
  onChange,
  placeholder = "选择期望表",
}: TableMultiSelectProps) {
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const [loadTables] = useLazyQuery(TABLES_DETAIL);

  useEffect(() => {
    let cancelled = false;

    async function fetchOptions() {
      if (datasources.length === 0) {
        setOptions([]);
        return;
      }

      setLoading(true);
      try {
        const names = new Set<string>();
        const targets = datasourceId
          ? datasources.filter((ds) => ds.id === datasourceId)
          : datasources;

        for (const ds of targets) {
          const { data } = await loadTables({ variables: { datasourceId: ds.id } });
          for (const table of data?.tablesDetail ?? []) {
            names.add(table.tableName);
          }
        }

        if (!cancelled) {
          setOptions([...names].sort());
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    fetchOptions();
    return () => {
      cancelled = true;
    };
  }, [datasourceId, datasources, loadTables]);

  useEffect(() => {
    const onDocClick = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  const toggleTable = (tableName: string) => {
    if (value.includes(tableName)) {
      onChange(value.filter((name) => name !== tableName));
    } else {
      onChange([...value, tableName]);
    }
  };

  const label = value.length > 0 ? value.join(", ") : placeholder;

  return (
    <div className="table-multi-select" ref={rootRef}>
      <button
        type="button"
        className="table-multi-select-trigger"
        onClick={() => setOpen((prev) => !prev)}
        title={label}
      >
        <span className="table-multi-select-label">{label}</span>
        <span className="table-multi-select-caret">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="table-multi-select-menu">
          {loading && <div className="table-multi-select-empty">加载表列表...</div>}
          {!loading && options.length === 0 && (
            <div className="table-multi-select-empty">暂无可用表，请先在元数据页维护</div>
          )}
          {!loading &&
            options.map((tableName) => (
              <label key={tableName} className="table-multi-select-item">
                <input
                  type="checkbox"
                  checked={value.includes(tableName)}
                  onChange={() => toggleTable(tableName)}
                />
                <span>{tableName}</span>
              </label>
            ))}
        </div>
      )}
    </div>
  );
}
