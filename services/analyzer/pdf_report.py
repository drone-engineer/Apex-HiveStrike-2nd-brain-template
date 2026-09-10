"""ULog 종합 분석 보고서를 한글 PDF로 렌더링한다."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from services.analyzer.schemas import AnalysisReport, ChartSeries, Severity

_FONT_CANDIDATES = (
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    Path("/Library/Fonts/Arial Unicode.ttf"),
    Path("/System/Library/Fonts/Supplemental/AppleGothic.ttf"),
    Path("/Library/Fonts/NanumGothic.ttf"),
    Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
    Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
)

_SEV_RGB: dict[Severity, tuple[int, int, int]] = {
    Severity.OK: (46, 160, 90),
    Severity.INFO: (80, 96, 128),
    Severity.WARNING: (212, 136, 24),
    Severity.CRITICAL: (196, 48, 48),
}


class PdfFontError(RuntimeError):
    """한글 TTF를 찾지 못하면 발생한다."""


def _iter_kr_fonts() -> list[Path]:
    return [path for path in _FONT_CANDIDATES if path.is_file()]


def render_analysis_pdf(report: AnalysisReport) -> bytes:
    """AnalysisReport를 A4 PDF 바이트로 변환한다."""

    fonts = _iter_kr_fonts()
    if not fonts:
        raise PdfFontError(
            "한글 PDF 폰트를 찾지 못했습니다. AppleGothic 또는 NanumGothic TTF가 필요합니다."
        )

    last_error: Exception | None = None
    pdf: _ReportPdf | None = None
    for font_path in fonts:
        try:
            candidate = _ReportPdf(report)
            candidate.add_font("HiveKR", "", str(font_path))
            pdf = candidate
            break
        except Exception as exc:
            last_error = exc
            continue
    if pdf is None:
        raise PdfFontError(f"한글 PDF 폰트를 등록하지 못했습니다. ({last_error})")

    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()
    pdf.render_body()
    return bytes(pdf.output())


def write_analysis_pdf(report: AnalysisReport, dest: str | Path) -> Path:
    path = Path(dest)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(render_analysis_pdf(report))
    return path


class _ReportPdf(FPDF):
    def __init__(self, report: AnalysisReport) -> None:
        super().__init__(format="A4", unit="mm")
        self.report = report

    def header(self) -> None:
        self.set_font("HiveKR", size=9)
        self.set_text_color(90, 102, 122)
        self.cell(
            0,
            6,
            "Apex HiveStrike  ULog 종합 분석 보고서",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        self.set_draw_color(245, 165, 36)
        self.set_line_width(0.6)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("HiveKR", size=8)
        self.set_text_color(120, 128, 140)
        self.cell(
            0,
            8,
            f"{self.page_no()}  ·  Canonical SSOT만 처방  ·  needs_review",
            align="C",
        )

    def render_body(self) -> None:
        report = self.report
        sev = report.overall_severity
        self.set_x(self.l_margin)
        self.set_font("HiveKR", size=16)
        self.set_text_color(20, 28, 44)
        self.multi_cell(self.epw, 8, f"{report.summary.filename}")
        self.set_font("HiveKR", size=11)
        rgb = _SEV_RGB.get(sev, (80, 96, 128))
        self.set_text_color(*rgb)
        self.cell(0, 7, f"종합 심각도  {sev.value.upper()}  ·  {report.report_id}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(50, 60, 76)
        self.set_font("HiveKR", size=10)
        meta = [
            f"비행 시간 {report.summary.duration_s}s",
            f"펌웨어 {report.summary.firmware or 'unknown'}",
            f"보드 {report.summary.board or 'unknown'}",
            f"토픽 {report.summary.topic_count}개",
            f"파라미터 {report.summary.parameter_count}개",
            f"드롭아웃 {report.summary.dropout_count}회",
        ]
        if report.summary.file_size_bytes:
            meta.append(f"파일 {report.summary.file_size_bytes:,} bytes")
        self.multi_cell(self.epw, 6, "  ·  ".join(meta))
        self.ln(2)

        self._heading("종합 요약")
        for line in report.executive_summary or ["(요약 없음)"]:
            self._bullet(line)

        kin = report.summary.kinematics
        if kin:
            self._heading("비행 규모")
            rows = [
                ("시동 시간", _fmt(kin.armed_s, "s")),
                ("수평 거리", _fmt(kin.distance_m, "m")),
                ("최대 수평속도", _fmt(kin.max_speed_mps, "m/s")),
                ("최대 |vz|", _fmt(kin.max_abs_vz_mps, "m/s")),
                (
                    "상대고도",
                    (
                        f"{kin.alt_min_m} ~ {kin.alt_max_m} m"
                        if kin.alt_min_m is not None and kin.alt_max_m is not None
                        else "—"
                    ),
                ),
            ]
            for label, value in rows:
                self._kv(label, value)

        self._heading("탐지된 이상")
        if not report.findings:
            self._bullet("탐지된 이상 없음")
        else:
            for item in report.findings:
                when = f"  t={item.t_s:.1f}s" if item.t_s is not None else ""
                self._bullet(f"[{item.severity.value}] {item.title}{when}")
                self._note(item.detail)

        self._heading("예상 문제점 및 대응 정비")
        if not report.risks:
            self._bullet("로그 기준 예상 문제 없음. Canonical 불일치는 아래 처방 절을 보십시오.")
        else:
            for risk in report.risks:
                self._bullet(
                    f"[{risk.severity.value}/{risk.likelihood}] {risk.problem}"
                )
                self._note(f"예상 영향: {risk.impact}")
                if risk.evidence_codes:
                    self._note("근거: " + ", ".join(risk.evidence_codes))
                for step in risk.inspect_now:
                    self._note("점검: " + step)
                if risk.canonical_actions:
                    for step in risk.canonical_actions:
                        self._note("Canonical: " + step)
                else:
                    self._note("Canonical: 해당 수치 없음")
                if risk.ssot_gap:
                    self._note("SSOT 공백: " + risk.ssot_gap)

        self._heading("Canonical 파라미터 처방")
        if not report.prescriptions:
            self._bullet("Canonical 대비 추가 처방 없음")
        else:
            for rx in report.prescriptions:
                name = rx.param_name or rx.kind
                arrow = "" if rx.prescribed_value is None else f" → {rx.prescribed_value}"
                src = f" ({rx.canonical_source})" if rx.canonical_source else ""
                self._bullet(f"{name}{arrow} — {rx.reason}{src}")

        self._heading("로그 파라미터 vs Canonical")
        if not report.canonical_deltas:
            self._bullet("Canonical에서 추출된 PX4 파라미터가 없습니다.")
        else:
            for delta in report.canonical_deltas:
                flag = "일치" if delta.matches else "불일치"
                self._bullet(
                    f"{delta.param_name}: 로그 {delta.log_value} / Canonical {delta.canonical_value} ({flag})"
                )

        self._heading("타임라인")
        events = report.timeline[:80]
        if not events:
            self._bullet("타임라인 이벤트 없음")
        else:
            for event in events:
                self._bullet(f"+{event.t_s:.1f}s [{event.kind}] {event.text}")

        self._heading("주요 시계열 통계")
        stats = report.metric_stats[:50]
        if not stats:
            self._bullet("추출된 시계열 통계 없음")
        else:
            self._table(
                ["metric", "topic", "min", "mean", "p95", "max"],
                [
                    [
                        f"{row.name}{f' ({row.unit})' if row.unit else ''}",
                        row.topic,
                        _num(row.min),
                        _num(row.mean),
                        _num(row.p95),
                        _num(row.max),
                    ]
                    for row in stats
                ],
                widths=[48, 42, 22, 22, 22, 22],
            )

        self._heading("기록 토픽")
        topics = report.topic_profiles[:80]
        if not topics:
            self._bullet("토픽 없음")
        else:
            self._table(
                ["topic", "n", "Hz", "fields"],
                [
                    [
                        f"{t.name}{f'[{t.instance}]' if t.instance else ''}",
                        str(t.samples),
                        "—" if t.rate_hz is None else str(t.rate_hz),
                        ", ".join(t.fields[:6]),
                    ]
                    for t in topics
                ],
                widths=[52, 22, 18, 86],
            )

        if report.notes:
            self._heading("분석 노트")
            for note in report.notes:
                self._bullet(note)

        charts = [c for c in report.charts if c.x and c.y][:10]
        if charts:
            self._heading("시계열 차트")
            for chart in charts:
                self._draw_chart(chart)

        self.ln(2)
        self.set_font("HiveKR", size=8)
        self.set_text_color(110, 118, 130)
        self.multi_cell(
            self.epw,
            5,
            "이 문서는 에이전트 자동 산출물이며 status: needs_review 입니다. "
            "수치 처방은 02_Canonical SSOT만 사용했고, Canonical에 없는 튜닝값은 발명하지 않았습니다.",
        )

    def _heading(self, title: str) -> None:
        self.ln(2)
        if self.get_y() > self.h - 32:
            self.add_page()
        self.set_x(self.l_margin)
        self.set_font("HiveKR", size=12)
        self.set_text_color(20, 28, 44)
        self.cell(0, 8, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(36, 48, 73)
        self.set_line_width(0.2)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(2)
        self.set_x(self.l_margin)

    def _bullet(self, text: str) -> None:
        self.set_x(self.l_margin)
        self.set_font("HiveKR", size=9)
        self.set_text_color(40, 48, 62)
        self.multi_cell(self.epw, 5, f"- {_clean(text)}")

    def _note(self, text: str) -> None:
        self.set_x(self.l_margin + 4)
        self.set_font("HiveKR", size=8)
        self.set_text_color(90, 98, 112)
        self.multi_cell(self.epw - 4, 4.5, _clean(text))
        self.set_x(self.l_margin)

    def _kv(self, label: str, value: str) -> None:
        self.set_x(self.l_margin)
        self.set_font("HiveKR", size=9)
        self.set_text_color(90, 98, 112)
        self.cell(36, 5, label)
        self.set_text_color(30, 38, 52)
        self.cell(self.epw - 36, 5, value, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def _table(self, headers: list[str], rows: list[list[str]], widths: list[float]) -> None:
        self.set_x(self.l_margin)
        self.set_font("HiveKR", size=8)
        self.set_fill_color(236, 240, 248)
        self.set_text_color(70, 78, 92)
        for head, width in zip(headers, widths):
            self.cell(width, 6, _clip(head, width), fill=True)
        self.ln(6)
        self.set_text_color(30, 38, 52)
        for idx, row in enumerate(rows):
            if self.get_y() > self.h - 20:
                self.add_page()
                self.set_font("HiveKR", size=8)
            fill = idx % 2 == 1
            if fill:
                self.set_fill_color(248, 250, 253)
            for value, width in zip(row, widths):
                self.cell(width, 5.5, _clip(value, width), fill=fill)
            self.ln(5.5)

    def _draw_chart(self, chart: ChartSeries) -> None:
        width = self.epw
        height = 42
        if self.get_y() + height + 12 > self.h - 16:
            self.add_page()
        self.set_font("HiveKR", size=9)
        self.set_text_color(30, 38, 52)
        self.cell(0, 6, chart.title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        x0 = self.l_margin
        y0 = self.get_y()
        self.set_draw_color(210, 216, 226)
        self.set_fill_color(250, 251, 253)
        self.rect(x0, y0, width, height, style="DF")
        xs = [float(v) for v in chart.x]
        ys = [float(v) for v in chart.y]
        n = min(len(xs), len(ys))
        if n >= 2:
            xs, ys = xs[:n], ys[:n]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            span_x = max(max_x - min_x, 1e-9)
            span_y = max(max_y - min_y, 1e-9)
            pad = 3
            pts: list[tuple[float, float]] = []
            for xv, yv in zip(xs, ys):
                px = x0 + pad + (xv - min_x) / span_x * (width - 2 * pad)
                py = y0 + height - pad - (yv - min_y) / span_y * (height - 2 * pad)
                pts.append((px, py))
            self.set_draw_color(245, 165, 36)
            self.set_line_width(0.4)
            for (ax, ay), (bx, by) in zip(pts, pts[1:]):
                self.line(ax, ay, bx, by)
            self.set_font("HiveKR", size=7)
            self.set_text_color(110, 118, 130)
            self.set_xy(x0 + 1, y0 + height - 4)
            self.cell(width / 2, 4, f"{chart.x_label}  {min_x:.2f}–{max_x:.2f}")
            self.set_xy(x0 + width / 2, y0 + 1)
            self.cell(width / 2 - 2, 4, f"{chart.y_label}  {min_y:.2f}–{max_y:.2f}", align="R")
        self.set_y(y0 + height + 4)


def _fmt(value: Optional[float], unit: str) -> str:
    return "—" if value is None else f"{value} {unit}"


def _num(value: float) -> str:
    if abs(value) >= 1000:
        return f"{value:.1f}"
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _clip(text: str, width_mm: float) -> str:
    cleaned = _clean(text)
    max_chars = max(4, int(width_mm / 1.7))
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1] + "..."


def _clean(text: str) -> str:
    return " ".join((text or "").replace("\t", " ").split())
