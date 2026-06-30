"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/", label: "概览" },
  { href: "/prompts", label: "Prompt 管理" },
  { href: "/metadata", label: "元数据" },
  { href: "/business", label: "业务数据" },
  { href: "/templates", label: "SQL 模板" },
  { href: "/rag-search", label: "向量检索" },
  { href: "/cache", label: "缓存监控" },
  { href: "/alerts", label: "RAG 告警" },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="layout">
      <aside className="sidebar">
        <h2>NL2SQL Admin</h2>
        <nav>
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={pathname === item.href ? "active" : ""}
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}
