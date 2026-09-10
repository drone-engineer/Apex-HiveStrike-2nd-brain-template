"use client";

import { useState, type ReactNode } from "react";
import {
  analyzeUlog,
  downloadReportPdf,
  type AnalysisReport,
  type MetricStats,
  type RiskItem,
  type Severity,
  type TimelineEvent,
  type TopicProfile,
} from "@/lib/api";
import { FlightCharts } from "@/components/FlightCharts";

const SEVERITY_COLOR: Record<Severity, string> = {
  ok: "text-hive-ok",
  info: "text-hive-text",
  warning: "text-hive-warn",
  critical: "text-hive-crit",
};

export function LogWorkbench() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<AnalysisReport | null>(null);

  const onFile = async (file: File | undefined) => {
    if (!file) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setReport(await analyzeUlog(file));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "분석 실패");
      setReport(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="space-y-4">
      <label className="flex cursor-pointer flex-col items-start gap-2 rounded-xl border border-dashed border-hive-accent/50 bg-hive-panel p-5">
        <span className="text-sm font-semibold text-hive-accent">PX4 ULog (.ulg) 업로드</span>
        <span className="text-xs text-hive-muted">
          전 토픽 스캔 후 종합 요약·타임라인·통계·차트와 Canonical 처방을 표시합니다.
        </span>
        <input
          type="file"
          accept=".ulg"
          className="text-sm text-hive-text file:mr-3 file:rounded-md file:border-0 file:bg-hive-accent file:px-3 file:py-1 file:text-sm file:font-semibold file:text-hive-bg"
          disabled={busy}
          onChange={(event) => void onFile(event.target.files?.[0])}
        />
      </label>
      {busy ? <p className="text-sm text-hive-muted">로그 전체를 스캔하는 중…</p> : null}
      {error ? (
        <pre className="overflow-x-auto rounded-xl border border-hive-crit/40 bg-hive-panel p-3 text-xs text-hive-crit">
          {error}
        </pre>
      ) : null}
      {report ? <ReportView report={report} /> : null}
    </section>
  );
}

function ReportView({ report }: { report: AnalysisReport }) {
  const kin = report.summary.kinematics;
  const [pdfBusy, setPdfBusy] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);

  const onDownloadPdf = async () => {
    setPdfBusy(true);
    setPdfError(null);
    try {
      await downloadReportPdf(report);
    } catch (err: unknown) {
      setPdfError(err instanceof Error ? err.message : "PDF 저장 실패");
    } finally {
      setPdfBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-hive-line bg-hive-panel p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className={`text-sm font-semibold uppercase ${SEVERITY_COLOR[report.overall_severity]}`}>
              {report.overall_severity}
            </p>
            <h3 className="mt-1 text-lg font-semibold">{report.summary.filename}</h3>
            <p className="mt-1 text-sm text-hive-muted">
              {report.summary.duration_s}s · {report.summary.firmware ?? "firmware unknown"} ·{" "}
              {report.summary.board ?? "board unknown"} · 토픽 {report.summary.topic_count} · 드롭아웃{" "}
              {report.summary.dropout_count ?? 0}
            </p>
          </div>
          <button
            type="button"
            onClick={() => void onDownloadPdf()}
            disabled={pdfBusy}
            className="rounded-md bg-hive-accent px-3 py-2 text-sm font-semibold text-hive-bg disabled:opacity-60"
          >
            {pdfBusy ? "PDF 만드는 중…" : "PDF 저장"}
          </button>
        </div>
        {report.discovery_path ? (
          <p className="mt-2 text-xs text-hive-muted">Discovery: {report.discovery_path}</p>
        ) : null}
        {report.pdf_path ? (
          <p className="text-xs text-hive-muted">PDF: {report.pdf_path}</p>
        ) : null}
        {pdfError ? <p className="mt-2 text-xs text-hive-crit">{pdfError}</p> : null}
        {report.executive_summary?.length ? (
          <ul className="mt-3 list-disc space-y-1 pl-5 text-sm">
            {report.executive_summary.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        ) : null}
      </div>

      {kin ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatChip label="시동 시간" value={fmt(kin.armed_s, "s")} />
          <StatChip label="수평 거리" value={fmt(kin.distance_m, "m")} />
          <StatChip label="최대 수평속도" value={fmt(kin.max_speed_mps, "m/s")} />
          <StatChip
            label="상대고도"
            value={
              kin.alt_min_m != null && kin.alt_max_m != null
                ? `${kin.alt_min_m} ~ ${kin.alt_max_m} m`
                : "—"
            }
          />
        </div>
      ) : null}

      <RiskPanel risks={report.risks ?? []} />

      <FlightCharts charts={report.charts ?? []} />

      <div className="grid gap-4 lg:grid-cols-2">
        <ListCard title="탐지된 이상">
          {report.findings.length === 0 ? (
            <li className="text-hive-muted">이상 없음</li>
          ) : (
            report.findings.map((item, idx) => (
              <li key={`${item.code}-${idx}`}>
                <span className={SEVERITY_COLOR[item.severity]}>[{item.severity}]</span> {item.title}
                {item.t_s != null ? (
                  <span className="text-hive-muted"> · t={item.t_s.toFixed(1)}s</span>
                ) : null}
                <p className="text-hive-muted">{item.detail}</p>
              </li>
            ))
          )}
        </ListCard>
        <ListCard title="Canonical 처방">
          {report.prescriptions.length === 0 ? (
            <li className="text-hive-muted">추가 처방 없음</li>
          ) : (
            report.prescriptions.map((item, idx) => (
              <li key={`${item.param_name ?? item.kind}-${idx}`}>
                {item.param_name ?? item.kind}
                {item.prescribed_value != null ? ` → ${item.prescribed_value}` : ""} — {item.reason}
              </li>
            ))
          )}
        </ListCard>
      </div>

      <TimelineCard events={report.timeline ?? []} />
      <MetricsTable stats={report.metric_stats ?? []} />
      <TopicsTable topics={report.topic_profiles ?? []} />
    </div>
  );
}

function RiskPanel({ risks }: { risks: RiskItem[] }) {
  return (
    <div className="rounded-xl border border-hive-line bg-hive-panel p-4">
      <h4 className="text-sm font-semibold text-hive-accent">예상 문제점 및 대응 정비</h4>
      {risks.length === 0 ? (
        <p className="mt-2 text-sm text-hive-muted">로그 기준 예상 문제 없음</p>
      ) : (
        <ul className="mt-3 space-y-4 text-sm">
          {risks.map((risk) => (
            <li key={risk.id} className="rounded-lg border border-hive-line/70 p-3">
              <p className={`font-semibold ${SEVERITY_COLOR[risk.severity]}`}>
                [{risk.severity}/{risk.likelihood}] {risk.problem}
              </p>
              <p className="mt-1 text-hive-muted">{risk.impact}</p>
              <p className="mt-2 text-xs font-semibold text-hive-accent">즉시 점검</p>
              <ul className="mt-1 list-disc space-y-1 pl-5">
                {risk.inspect_now.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ul>
              <p className="mt-2 text-xs font-semibold text-hive-accent">Canonical 적용</p>
              {risk.canonical_actions.length ? (
                <ul className="mt-1 list-disc space-y-1 pl-5">
                  {risk.canonical_actions.map((step) => (
                    <li key={step}>{step}</li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-hive-muted">해당 Canonical 수치 없음</p>
              )}
              {risk.ssot_gap ? (
                <p className="mt-2 text-xs text-hive-warn">SSOT 공백: {risk.ssot_gap}</p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function fmt(value: number | null | undefined, unit: string): string {
  return value == null ? "—" : `${value} ${unit}`;
}

function StatChip({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-hive-line bg-hive-panel p-3">
      <p className="text-xs text-hive-muted">{label}</p>
      <p className="mt-1 text-sm font-semibold">{value}</p>
    </div>
  );
}

function TimelineCard({ events }: { events: TimelineEvent[] }) {
  return (
    <div className="rounded-xl border border-hive-line bg-hive-panel p-4">
      <h4 className="text-sm font-semibold text-hive-accent">타임라인</h4>
      {events.length === 0 ? (
        <p className="mt-2 text-sm text-hive-muted">이벤트 없음</p>
      ) : (
        <ul className="mt-2 max-h-72 space-y-1 overflow-y-auto text-sm">
          {events.map((event, idx) => (
            <li key={`${event.kind}-${event.t_s}-${idx}`}>
              <span className="text-hive-muted">+{event.t_s.toFixed(1)}s</span>{" "}
              <span className={SEVERITY_COLOR[event.severity]}>[{event.kind}]</span> {event.text}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function MetricsTable({ stats }: { stats: MetricStats[] }) {
  const rows = stats.slice(0, 60);
  return (
    <div className="rounded-xl border border-hive-line bg-hive-panel p-4">
      <h4 className="text-sm font-semibold text-hive-accent">시계열 통계</h4>
      <p className="mt-1 text-xs text-hive-muted">
        {stats.length}개 필드 요약{stats.length > rows.length ? ` · 상위 ${rows.length}개 표시` : ""}
      </p>
      {rows.length === 0 ? (
        <p className="mt-2 text-sm text-hive-muted">통계 없음</p>
      ) : (
        <div className="mt-2 max-h-80 overflow-auto">
          <table className="w-full min-w-[640px] text-left text-xs">
            <thead className="text-hive-muted">
              <tr>
                <th className="pb-2 pr-3">metric</th>
                <th className="pb-2 pr-3">topic</th>
                <th className="pb-2 pr-3">min</th>
                <th className="pb-2 pr-3">mean</th>
                <th className="pb-2 pr-3">p95</th>
                <th className="pb-2">max</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={`${row.topic}-${row.name}`} className="border-t border-hive-line/60">
                  <td className="py-1 pr-3 font-mono">
                    {row.name}
                    {row.unit ? ` (${row.unit})` : ""}
                  </td>
                  <td className="py-1 pr-3 text-hive-muted">{row.topic}</td>
                  <td className="py-1 pr-3">{row.min}</td>
                  <td className="py-1 pr-3">{row.mean}</td>
                  <td className="py-1 pr-3">{row.p95}</td>
                  <td className="py-1">{row.max}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function TopicsTable({ topics }: { topics: TopicProfile[] }) {
  return (
    <div className="rounded-xl border border-hive-line bg-hive-panel p-4">
      <h4 className="text-sm font-semibold text-hive-accent">기록 토픽</h4>
      <p className="mt-1 text-xs text-hive-muted">{topics.length}개 데이터셋</p>
      {topics.length === 0 ? (
        <p className="mt-2 text-sm text-hive-muted">토픽 없음</p>
      ) : (
        <div className="mt-2 max-h-72 overflow-auto">
          <table className="w-full min-w-[520px] text-left text-xs">
            <thead className="text-hive-muted">
              <tr>
                <th className="pb-2 pr-3">topic</th>
                <th className="pb-2 pr-3">n</th>
                <th className="pb-2 pr-3">Hz</th>
                <th className="pb-2">fields</th>
              </tr>
            </thead>
            <tbody>
              {topics.map((topic) => (
                <tr key={`${topic.name}-${topic.instance}`} className="border-t border-hive-line/60">
                  <td className="py-1 pr-3 font-mono">
                    {topic.name}
                    {topic.instance ? `[${topic.instance}]` : ""}
                  </td>
                  <td className="py-1 pr-3">{topic.samples}</td>
                  <td className="py-1 pr-3">{topic.rate_hz ?? "—"}</td>
                  <td className="py-1 text-hive-muted">{topic.fields.slice(0, 8).join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function ListCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-xl border border-hive-line bg-hive-panel p-4">
      <h4 className="text-sm font-semibold text-hive-accent">{title}</h4>
      <ul className="mt-2 space-y-2 text-sm">{children}</ul>
    </div>
  );
}
