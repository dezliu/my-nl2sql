"use client";

import { useEffect, useMemo, useRef, useState } from "react";

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
  searchPlaceholder?: string;
  loading?: boolean;
  emptyMessage?: string;
  noResultsMessage?: string;
  serverSearch?: boolean;
  onSearchChange?: (query: string) => void;
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
  placeholder = "请选择",
  searchPlaceholder = "搜索...",
  loading = false,
  emptyMessage = "暂无选项",
  noResultsMessage = "无匹配结果",
  serverSearch = false,
  onSearchChange,
}: SearchableMultiSelectProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDocClick = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  useEffect(() => {
    if (!open) {
      setSearch("");
      onSearchChange?.("");
    }
  }, [open, onSearchChange]);

  const optionMap = useMemo(() => new Map(options.map((o) => [o.value, o])), [options]);

  const displayOptions = useMemo(() => {
    const selectedExtras = value
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
  }, [options, optionMap, value, search, serverSearch]);

  const toggle = (optionValue: string) => {
    if (value.includes(optionValue)) {
      onChange(value.filter((v) => v !== optionValue));
    } else {
      onChange([...value, optionValue]);
    }
  };

  const triggerLabel =
    value.length > 0
      ? value
          .map((id) => optionMap.get(id)?.label ?? `#${id}`)
          .join(", ")
      : placeholder;

  const handleSearchChange = (query: string) => {
    setSearch(query);
    if (serverSearch) {
      onSearchChange?.(query);
    }
  };

  return (
    <div className="searchable-multi-select" ref={rootRef}>
      <button
        type="button"
        className="searchable-multi-select-trigger"
        onClick={() => setOpen((prev) => !prev)}
        title={triggerLabel}
      >
        <span className="searchable-multi-select-label">{triggerLabel}</span>
        <span className="searchable-multi-select-caret">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="searchable-multi-select-menu">
          <input
            type="text"
            className="searchable-multi-select-search"
            placeholder={searchPlaceholder}
            value={search}
            onChange={(e) => handleSearchChange(e.target.value)}
            onClick={(e) => e.stopPropagation()}
            autoFocus
          />
          {loading && <div className="searchable-multi-select-empty">加载中...</div>}
          {!loading && options.length === 0 && search.trim() === "" && (
            <div className="searchable-multi-select-empty">{emptyMessage}</div>
          )}
          {!loading && displayOptions.length === 0 && (
            <div className="searchable-multi-select-empty">{noResultsMessage}</div>
          )}
          {!loading &&
            displayOptions.map((option) => (
              <label key={option.value} className="searchable-multi-select-item">
                <input
                  type="checkbox"
                  checked={value.includes(option.value)}
                  onChange={() => toggle(option.value)}
                />
                <span>{option.label}</span>
              </label>
            ))}
        </div>
      )}
    </div>
  );
}
