"use client";

import { useEffect, useMemo, useState } from "react";

import { AdminModal } from "./AdminModal";

export type SearchableOption = {
  value: string;
  label: string;
  keywords?: string;
};

type SearchableMultiSelectProps = {
  options: SearchableOption[];
  value: string[];
  onChange: (value: string[]) => void;
  placeholder?: string;
  title?: string;
  searchPlaceholder?: string;
  loading?: boolean;
  emptyMessage?: string;
  noResultsMessage?: string;
  serverSearch?: boolean;
  onSearchChange?: (query: string) => void;
  onOpen?: () => void;
  modalWidth?: number;
};

function matchesQuery(option: SearchableOption, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const haystack = `${option.label} ${option.keywords ?? ""} ${option.value}`.toLowerCase();
  return haystack.includes(q);
}

export function SearchableMultiSelect({
  options,
  value,
  onChange,
  placeholder = "点击选择",
  title = "请选择",
  searchPlaceholder = "搜索...",
  loading = false,
  emptyMessage = "暂无选项",
  noResultsMessage = "无匹配结果",
  serverSearch = false,
  onSearchChange,
  onOpen,
  modalWidth = 760,
}: SearchableMultiSelectProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [draft, setDraft] = useState<string[]>(value);

  useEffect(() => {
    if (open) {
      setDraft(value);
      setSearch("");
      onSearchChange?.("");
      onOpen?.();
    }
  }, [open, value, onSearchChange, onOpen]);

  const optionMap = useMemo(() => new Map(options.map((o) => [o.value, o])), [options]);

  const displayOptions = useMemo(() => {
    const selectedExtras = draft
      .filter((id) => !optionMap.has(id))
      .map((id) => ({ value: id, label: `#${id}` }));

    const base = [...selectedExtras, ...options];
    const seen = new Set<string>();
    const unique = base.filter((o) => {
      if (seen.has(o.value)) return false;
      seen.add(o.value);
      return true;
    });

    if (serverSearch) return unique;
    return unique.filter((o) => matchesQuery(o, search));
  }, [options, optionMap, draft, search, serverSearch]);

  const toggleDraft = (optionValue: string) => {
    setDraft((prev) =>
      prev.includes(optionValue) ? prev.filter((v) => v !== optionValue) : [...prev, optionValue]
    );
  };

  const handleSearchChange = (query: string) => {
    setSearch(query);
    if (serverSearch) {
      onSearchChange?.(query);
    }
  };

  const selectAllVisible = () => {
    const visibleValues = displayOptions.map((o) => o.value);
    setDraft((prev) => [...new Set([...prev, ...visibleValues])]);
  };

  const clearDraft = () => setDraft([]);

  const confirm = () => {
    onChange(draft);
    setOpen(false);
  };

  const removeTag = (optionValue: string) => {
    onChange(value.filter((v) => v !== optionValue));
  };

  return (
    <div className="picker-field">
      <button type="button" className="picker-trigger-btn" onClick={() => setOpen(true)}>
        {value.length > 0 ? `已选 ${value.length} 项 · 点击修改` : placeholder}
      </button>
      {value.length > 0 && (
        <div className="picker-tags">
          {value.map((id) => (
            <span key={id} className="picker-tag">
              {optionMap.get(id)?.label ?? `#${id}`}
              <button
                type="button"
                className="picker-tag-remove"
                onClick={() => removeTag(id)}
                aria-label="移除"
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      <AdminModal open={open} title={title} onClose={() => setOpen(false)} width={modalWidth}>
        <input
          type="text"
          className="picker-search"
          placeholder={searchPlaceholder}
          value={search}
          onChange={(e) => handleSearchChange(e.target.value)}
          autoFocus
        />

        <div className="picker-toolbar">
          <span>已选 {draft.length} 项</span>
          <div className="picker-toolbar-actions">
            <button type="button" className="link-btn" onClick={selectAllVisible}>
              全选当前列表
            </button>
            <button type="button" className="link-btn" onClick={clearDraft}>
              清空
            </button>
          </div>
        </div>

        <div className="picker-list">
          {loading && <div className="picker-empty">加载中...</div>}
          {!loading && options.length === 0 && search.trim() === "" && (
            <div className="picker-empty">{emptyMessage}</div>
          )}
          {!loading && displayOptions.length === 0 && (
            <div className="picker-empty">{noResultsMessage}</div>
          )}
          {!loading &&
            displayOptions.map((option) => (
              <label key={option.value} className="picker-item">
                <input
                  type="checkbox"
                  checked={draft.includes(option.value)}
                  onChange={() => toggleDraft(option.value)}
                />
                <span>{option.label}</span>
              </label>
            ))}
        </div>

        <div className="picker-footer">
          <button type="button" className="btn btn-sm" onClick={() => setOpen(false)}>
            取消
          </button>
          <button type="button" className="btn btn-sm btn-success" onClick={confirm}>
            确定
          </button>
        </div>
      </AdminModal>
    </div>
  );
}
