"use client";

import { useEffect, useState } from "react";
import { fetchVaultOverview, type VaultOverview } from "@/lib/api";

export function VaultPanel() {
  const [data, setData] = useState<VaultOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchVaultOverview()
      .then(setData)
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "볼트를 읽지 못했습니다.");
      });
  }, []);

  if (error) {
    return (
      <div className="rounded-xl border border-hive-crit/40 bg-hive-panel p-4 text-sm text-hive-crit">
        {error} API(`127.0.0.1:8000`)가 켜져 있는지 확인하세요.
      </div>
    );
  }

  if (!data) {
    return <div className="text-sm text-hive-muted">볼트 현황을 불러오는 중…</div>;
  }

  const cards = [
    { label: "Evidence", value: data.evidence },
    { label: "Discovery", value: data.discovery },
    { label: "Canonical", value: data.canonical },
    { label: "Lint", value: data.lint_issues },
  ];

  return (
    <section className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((card) => (
          <div key={card.label} className="rounded-xl border border-hive-line bg-hive-panel p-4">
            <p className="text-xs uppercase tracking-wide text-hive-muted">{card.label}</p>
            <p className="mt-1 text-2xl font-semibold text-hive-text">{card.value}</p>
          </div>
        ))}
      </div>
      <div className="rounded-xl border border-hive-line bg-hive-panel p-4">
        <h2 className="text-sm font-semibold text-hive-accent">검토 대기 Discovery ({data.pending_count})</h2>
        <ul className="mt-3 space-y-2 text-sm">
          {data.pending.length === 0 ? (
            <li className="text-hive-muted">대기 문서 없음</li>
          ) : (
            data.pending.map((item) => (
              <li key={`${item.category}-${item.id}`} className="flex gap-2 text-hive-text">
                <span className="shrink-0 text-hive-muted">[{item.decision}]</span>
                <span className="truncate">
                  {item.category} · {item.title}
                </span>
              </li>
            ))
          )}
        </ul>
      </div>
    </section>
  );
}
