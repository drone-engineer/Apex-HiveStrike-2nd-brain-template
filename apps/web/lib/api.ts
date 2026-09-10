export type Severity = "ok" | "info" | "warning" | "critical";

export type ChartSeries = {
  id: string;
  title: string;
  x_label: string;
  y_label: string;
  kind: "line" | "path";
  x: number[];
  y: number[];
  y2?: number[] | null;
};

export type FlightKinematics = {
  armed_s?: number | null;
  distance_m?: number | null;
  max_speed_mps?: number | null;
  max_abs_vz_mps?: number | null;
  alt_min_m?: number | null;
  alt_max_m?: number | null;
  alt_range_m?: number | null;
};

export type TimelineEvent = {
  t_s: number;
  kind: "mode" | "arming" | "failsafe" | "log" | "dropout";
  text: string;
  severity: Severity;
};

export type TopicProfile = {
  name: string;
  instance: number;
  samples: number;
  rate_hz?: number | null;
  duration_s?: number | null;
  fields: string[];
};

export type MetricStats = {
  name: string;
  topic: string;
  unit?: string | null;
  samples: number;
  min: number;
  max: number;
  mean: number;
  std: number;
  p95: number;
};

export type RiskItem = {
  id: string;
  problem: string;
  severity: Severity;
  likelihood: "observed" | "likely" | "possible";
  impact: string;
  evidence_codes: string[];
  inspect_now: string[];
  canonical_actions: string[];
  ssot_gap?: string | null;
};

export type AnalysisReport = {
  report_id: string;
  overall_severity: Severity;
  executive_summary: string[];
  summary: {
    filename: string;
    duration_s: number;
    firmware?: string | null;
    board?: string | null;
    topic_count: number;
    parameter_count: number;
    logged_event_count?: number;
    dropout_count?: number;
    file_size_bytes?: number | null;
    kinematics?: FlightKinematics | null;
  };
  findings: Array<{
    code: string;
    title: string;
    severity: Severity;
    detail: string;
    measured_value?: number | null;
    threshold?: number | null;
    unit?: string | null;
    t_s?: number | null;
  }>;
  risks: RiskItem[];
  prescriptions: Array<{
    kind: string;
    param_name?: string | null;
    prescribed_value?: number | null;
    reason: string;
    canonical_source?: string | null;
  }>;
  canonical_deltas: Array<{
    param_name: string;
    log_value?: number | null;
    canonical_value: number;
    matches: boolean;
  }>;
  timeline: TimelineEvent[];
  topic_profiles: TopicProfile[];
  metric_stats: MetricStats[];
  notes: string[];
  discovery_path?: string | null;
  pdf_path?: string | null;
  charts: ChartSeries[];
};

export type VaultOverview = {
  evidence: number;
  discovery: number;
  canonical: number;
  lint_issues: number;
  pending_count: number;
  pending: Array<{
    id: string;
    title: string;
    category: string;
    decision: string;
  }>;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export async function fetchVaultOverview(): Promise<VaultOverview> {
  const res = await fetch(`${API_BASE}/vault/overview`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error("볼트 현황을 불러오지 못했습니다.");
  }
  return res.json();
}

export async function downloadReportPdf(report: AnalysisReport): Promise<void> {
  const res = await fetch(`${API_BASE}/logs/report/pdf`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(report),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || "PDF를 만들지 못했습니다.");
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${report.report_id}.pdf`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export async function analyzeUlog(file: File): Promise<AnalysisReport> {
  const body = new FormData();
  body.append("file", file);
  const res = await fetch(`${API_BASE}/logs/analyze?save_report=true`, {
    method: "POST",
    body,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || "로그 분석에 실패했습니다.");
  }
  return res.json();
}
