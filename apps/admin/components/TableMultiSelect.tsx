"use client";

import { gql, useLazyQuery } from "@apollo/client";
import { useEffect, useMemo, useState } from "react";

import { SearchableMultiSelect } from "./SearchableMultiSelect";

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
  const [options, setOptions] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
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

  const selectOptions = useMemo(
    () => options.map((tableName) => ({ value: tableName, label: tableName })),
    [options]
  );

  return (
    <SearchableMultiSelect
      options={selectOptions}
      value={value}
      onChange={onChange}
      placeholder={placeholder}
      searchPlaceholder="搜索表名..."
      loading={loading}
      emptyMessage="暂无可用表，请先在元数据页维护"
      noResultsMessage="无匹配表名"
    />
  );
}
