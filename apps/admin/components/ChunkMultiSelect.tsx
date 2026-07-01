"use client";

import { gql, useLazyQuery } from "@apollo/client";
import { useCallback, useEffect, useMemo, useState } from "react";

import { SearchableMultiSelect } from "./SearchableMultiSelect";

const RAG_EVAL_CHUNKS = gql`
  query RagEvalChunks($datasourceId: Int, $search: String, $limit: Int) {
    ragEvalChunks(datasourceId: $datasourceId, search: $search, limit: $limit) {
      id
      label
      docType
      title
    }
  }
`;

type ChunkMultiSelectProps = {
  datasourceId: number | null;
  value: number[];
  onChange: (chunkIds: number[]) => void;
  placeholder?: string;
};

export function ChunkMultiSelect({
  datasourceId,
  value,
  onChange,
  placeholder = "选择期望 chunk（可多选）",
}: ChunkMultiSelectProps) {
  const [search, setSearch] = useState("");
  const [chunks, setChunks] = useState<
    { id: number; label: string; docType: string; title: string }[]
  >([]);
  const [loadChunks, { loading }] = useLazyQuery(RAG_EVAL_CHUNKS);

  const fetchChunks = useCallback(
    async (query: string) => {
      const { data } = await loadChunks({
        variables: {
          datasourceId,
          search: query.trim() || null,
          limit: 200,
        },
      });
      setChunks(data?.ragEvalChunks ?? []);
    },
    [datasourceId, loadChunks]
  );

  useEffect(() => {
    const timer = window.setTimeout(() => {
      fetchChunks(search);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [search, fetchChunks]);

  const selectOptions = useMemo(
    () =>
      chunks.map((chunk) => ({
        value: String(chunk.id),
        label: chunk.label,
        keywords: `${chunk.docType} ${chunk.title}`,
      })),
    [chunks]
  );

  const stringValue = useMemo(() => value.map(String), [value]);

  const handleOpen = useCallback(() => {
    void fetchChunks("");
  }, [fetchChunks]);

  return (
    <SearchableMultiSelect
      options={selectOptions}
      value={stringValue}
      onChange={(ids) => onChange(ids.map(Number).filter((n) => !Number.isNaN(n)))}
      placeholder={placeholder}
      title="选择期望 chunk"
      searchPlaceholder="搜索 chunk ID / 类型 / 标题..."
      loading={loading}
      emptyMessage="暂无已索引 chunk，请先在元数据或业务页入库"
      noResultsMessage="无匹配 chunk"
      serverSearch
      onSearchChange={setSearch}
      onOpen={handleOpen}
      modalWidth={860}
    />
  );
}
