"""PX4 ULog(.ulg) 이상 진단 및 Canonical 파라미터 처방 엔진.

PROJECT_CONTEXT Priority 1:
  - 진동 클리핑(Vibration Clipping)
  - EKF2 혁신 게이트 초과
  - 전압 드롭
  - knowledge/02_Canonical 수치와 대조한 처방 리포트

탐지 게이트(이상이 '발생했는지')와 처방값(무엇을 '어떻게 고칠지')의 출처를 분리한다.
- 탐지: PX4 EKF2가 test_ratio>1.0을 게이트 실패로 정의하는 펌웨어 규칙, 로그 자체 BAT_* 임계값
- 처방: 오직 02_Canonical (reviewed: true) 수치. Canonical에 없으면 수치를 발명하지 않는다.
"""

from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np
from pyulog import ULog

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.analyzer.schemas import (
    AnalysisReport,
    AnomalyFinding,
    FlightSummary,
    ParamDelta,
    ParameterPrescription,
    Severity,
)

CANONICAL_DIR = REPO_ROOT / "knowledge" / "02_Canonical"

# PX4 EKF2: test_ratio = innovation / gate. 1.0을 넘으면 해당 보조 센서 게이트 실패.
EKF2_GATE_FAIL = 1.0
EKF2_GATE_WARN = 0.5
# PX4 Flight Review가 estimator_status.vibe 피크에 쓰는 경고/실패 라인.
# Canonical 처방값이 아니라 '탐지용' 게이트다.
VIBE_PEAK_WARN = 15.0
VIBE_PEAK_FAIL = 30.0
# 전류 급증 구간에서 팩 전압이 이 값 이상 꺼지면 인러시 드롭으로 본다.
VOLTAGE_SAG_V = 0.5

_PARAM_RE = re.compile(
    r"(?<![A-Z0-9_])([A-Z][A-Z0-9_]{2,})(?:\s*(?:(?i:set to)|=|:)|을|를)\s*(-?\d+(?:\.\d+)?)",
)
_RTL_ALT_RE = re.compile(
    r"(?:minimum\s+)?RTL\s+altitude[^\d]{0,48}(\d+(?:\.\d+)?)\s*(?:m|meters?|미터)",
    re.IGNORECASE,
)
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
# 로그 메시지에서 이상 징후만 추려 리포트에 남긴다.
_EVENT_HINTS = (
    "failsafe",
    "ekf",
    "gps",
    "clip",
    "battery",
    "baro",
    "innovation",
    "shock",
    "voltage",
    "rtl",
    "land",
    "kill",
)


class ULogParseError(Exception):
    """ULog 파싱/검증 실패. API 계층에서 HTTP 상태 코드로 변환한다."""

    def __init__(self, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class CanonicalParam:
    name: str
    value: float
    source_id: str
    source_file: str
    evidence: str
    unit: Optional[str] = None
    aliases: tuple[str, ...] = ()


@dataclass
class HardwareGuideline:
    topic: str
    text: str
    source_id: str
    source_file: str


@dataclass
class CanonicalCatalog:
    """02_Canonical에서 추출한 SSOT. Discovery/Evidence 수치는 넣지 않는다."""

    params: dict[str, CanonicalParam] = field(default_factory=dict)
    hardware: list[HardwareGuideline] = field(default_factory=list)
    source_docs: list[str] = field(default_factory=list)

    def get(self, name: str) -> Optional[CanonicalParam]:
        if name in self.params:
            return self.params[name]
        for param in self.params.values():
            if name in param.aliases:
                return param
        return None


def _frontmatter_field(fm: str, key: str) -> Optional[str]:
    match = re.search(rf"^{key}:\s*(.+)$", fm, re.MULTILINE)
    if not match:
        return None
    return match.group(1).strip().strip("\"'")


def _is_verified_canonical(fm: str) -> bool:
    """인간 검증을 통과한 Canonical만 SSOT로 채택한다."""

    status = (_frontmatter_field(fm, "status") or "").lower()
    reviewed = (_frontmatter_field(fm, "reviewed") or "").lower()
    return reviewed == "true" and status in {"verified", "canonical"}


def load_canonical_catalog(canonical_dir: Path | None = None) -> CanonicalCatalog:
    """knowledge/02_Canonical 마크다운에서 PX4 파라미터와 하드웨어 지침을 추출한다."""

    root = canonical_dir or CANONICAL_DIR
    catalog = CanonicalCatalog()
    if not root.is_dir():
        return catalog

    for path in sorted(root.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        fm_match = _FRONTMATTER_RE.match(text)
        fm = fm_match.group(1) if fm_match else ""
        if fm and not _is_verified_canonical(fm):
            continue

        doc_id = _frontmatter_field(fm, "id") or path.stem
        source_file = path.stem
        catalog.source_docs.append(source_file)
        body = text[fm_match.end() :] if fm_match else text

        for match in _PARAM_RE.finditer(body):
            name = match.group(1).upper()
            value = float(match.group(2))
            catalog.params[name] = CanonicalParam(
                name=name,
                value=value,
                source_id=doc_id,
                source_file=source_file,
                evidence=match.group(0).strip(),
            )

        rtl_alt = _RTL_ALT_RE.search(body)
        if rtl_alt and "RTL_RETURN_ALT" not in catalog.params:
            catalog.params["RTL_RETURN_ALT"] = CanonicalParam(
                name="RTL_RETURN_ALT",
                value=float(rtl_alt.group(1)),
                source_id=doc_id,
                source_file=source_file,
                evidence=rtl_alt.group(0).strip(),
                unit="m",
                aliases=("RTL_ALT",),
            )

        if any(token in body for token in ("전압 강하", "독립", "BEC")):
            catalog.hardware.append(
                HardwareGuideline(
                    topic="voltage_rail",
                    text=(
                        "모터 급기동 시 전압 강하로 인한 SBC 리셋을 방지하려면 "
                        "FC 전원선과 SBC 전원선을 완전히 분리된 독립 BEC로 구성한다."
                    ),
                    source_id=doc_id,
                    source_file=source_file,
                )
            )

    return catalog


def _severity_rank(severity: Severity) -> int:
    return {
        Severity.OK: 0,
        Severity.INFO: 1,
        Severity.WARNING: 2,
        Severity.CRITICAL: 3,
    }[severity]


def _max_severity(items: Iterable[Severity]) -> Severity:
    ranked = list(items)
    if not ranked:
        return Severity.OK
    return max(ranked, key=_severity_rank)


def _finite(arr: np.ndarray) -> np.ndarray:
    flat = np.asarray(arr, dtype=float).reshape(-1)
    return flat[np.isfinite(flat)]


def _series(data: dict[str, np.ndarray], *candidates: str) -> Optional[np.ndarray]:
    """ULog 필드명 차이(vibe[0] vs vibe_0)를 흡수한다."""

    for name in candidates:
        if name in data:
            return np.asarray(data[name])
    return None


def _indexed(data: dict[str, np.ndarray], base: str, index: int) -> Optional[np.ndarray]:
    return _series(data, f"{base}[{index}]", f"{base}_{index}", f"{base}{index}")


def _try_dataset(ulog: ULog, name: str, multi_instance: int = 0) -> Optional[ULog.Data]:
    try:
        return ulog.get_dataset(name, multi_instance=multi_instance)
    except (KeyError, IndexError, ValueError):
        return None


def _iter_datasets(ulog: ULog, name: str) -> list[ULog.Data]:
    return [ds for ds in ulog.data_list if ds.name == name]


def _param(ulog: ULog, *names: str) -> Optional[float]:
    params = ulog.initial_parameters or {}
    for name in names:
        if name in params:
            try:
                return float(params[name])
            except (TypeError, ValueError):
                return None
    return None


def _info(ulog: ULog, key: str) -> Optional[str]:
    raw = (ulog.msg_info_dict or {}).get(key)
    if raw is None:
        return None
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return str(raw)


class ULogAnalyzer:
    """PX4 ULog를 파싱해 이상 진단 + Canonical 처방 리포트를 만든다."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = Path(repo_root) if repo_root else REPO_ROOT
        self.canonical_dir = self.repo_root / "knowledge" / "02_Canonical"
        self.discovery_dir = (
            self.repo_root / "knowledge" / "03_Discovery" / "06_Troubleshooting"
        )

    def analyze(
        self,
        ulog_path: str | Path,
        original_filename: str | None = None,
        save_report: bool = True,
    ) -> AnalysisReport:
        """
        [동작] .ulg 파일을 파싱하고 진동/EKF2/전압 이상을 탐지한 뒤 Canonical과 대조한다.
        [이유] 처방 수치가 Discovery/모델 추정으로 새면 SSOT가 붕괴되므로 Canonical만 사용한다.
        [근거] AGENTS.md 지식 라이프사이클, PROJECT_CONTEXT Priority 1.
        """

        path = Path(ulog_path)
        filename = original_filename or path.name
        self._validate_filename(filename)
        if not path.is_file():
            raise ULogParseError(f"로그 파일을 찾을 수 없습니다: {path}", status_code=404)
        if path.stat().st_size < 16:
            raise ULogParseError(
                "업로드된 파일이 비어 있거나 ULog 헤더(16바이트)를 포함하지 않습니다."
            )

        try:
            ulog = ULog(str(path), disable_str_exceptions=True)
        except Exception as exc:  # pyulog는 손상 파일에 TypeError 등을 던진다.
            raise ULogParseError(
                f"ULog 파일을 파싱할 수 없습니다. "
                f"파일이 손상되었거나 PX4 ULog(.ulg) 형식이 아닙니다. ({exc})"
            ) from exc

        return self._analyze_parsed(ulog, filename, save_report=save_report)

    def _analyze_parsed(
        self,
        ulog: ULog,
        filename: str,
        save_report: bool,
    ) -> AnalysisReport:
        catalog = load_canonical_catalog(self.canonical_dir)
        findings: list[AnomalyFinding] = []
        notes: list[str] = []

        findings.extend(self._detect_vibration(ulog, notes))
        findings.extend(self._detect_ekf2_gates(ulog, notes))
        findings.extend(self._detect_voltage(ulog, notes))
        findings.extend(self._detect_failsafe_flags(ulog))

        deltas = self._compare_canonical_params(ulog, catalog)
        prescriptions = self._build_prescriptions(ulog, catalog, findings, deltas)
        events = self._collect_logged_events(ulog)
        summary = self._build_summary(ulog, filename)

        overall = _max_severity([f.severity for f in findings] or [Severity.OK])
        if overall == Severity.OK and any(not d.matches for d in deltas):
            overall = Severity.WARNING

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_id = f"ULOG-{stamp}"
        report = AnalysisReport(
            report_id=report_id,
            overall_severity=overall,
            summary=summary,
            findings=findings,
            prescriptions=prescriptions,
            canonical_deltas=deltas,
            logged_events=events,
            canonical_docs_used=catalog.source_docs,
            notes=notes,
        )

        if save_report:
            report.discovery_path = self._write_discovery_report(report, catalog)

        return report

    @staticmethod
    def _validate_filename(filename: str) -> None:
        lowered = filename.lower()
        if lowered.endswith(".tlog") or lowered.endswith(".bin"):
            raise ULogParseError(
                ".tlog/.bin(ArduPilot·MAVLink) 분석은 다음 단계에서 지원합니다. "
                "현재는 PX4 ULog(.ulg)만 분석할 수 있습니다.",
                status_code=400,
            )
        if not lowered.endswith(".ulg"):
            raise ULogParseError(
                "PX4 ULog(.ulg) 파일만 업로드할 수 있습니다.",
                status_code=400,
            )

    def _build_summary(self, ulog: ULog, filename: str) -> FlightSummary:
        duration_s = max(0.0, (ulog.last_timestamp - ulog.start_timestamp) / 1e6)
        topics = sorted({ds.name for ds in ulog.data_list})
        return FlightSummary(
            filename=filename,
            duration_s=round(duration_s, 3),
            firmware=_info(ulog, "ver_sw") or _info(ulog, "ver_sw_release"),
            board=_info(ulog, "ver_hw"),
            start_timestamp_us=int(ulog.start_timestamp),
            topic_count=len(topics),
            parameter_count=len(ulog.initial_parameters or {}),
            available_topics=topics[:80],
            logged_event_count=len(ulog.logged_messages or []),
        )

    def _detect_vibration(self, ulog: ULog, notes: list[str]) -> list[AnomalyFinding]:
        findings: list[AnomalyFinding] = []

        clip_total = 0
        clip_topics: list[str] = []
        for ds in _iter_datasets(ulog, "vehicle_imu_status"):
            for axis in range(3):
                accel = _indexed(ds.data, "accel_clipping", axis)
                gyro = _indexed(ds.data, "gyro_clipping", axis)
                for label, series in (("accel", accel), ("gyro", gyro)):
                    if series is None or series.size == 0:
                        continue
                    finite = _finite(series)
                    if finite.size == 0:
                        continue
                    delta = int(max(0.0, float(finite[-1] - finite[0])))
                    peak = int(float(np.max(finite)))
                    count = max(delta, peak if delta == 0 and peak > 0 else delta)
                    if count > 0:
                        clip_total += count
                        clip_topics.append(f"{ds.name}[{ds.multi_id}].{label}_clipping[{axis}]={count}")

        for ds in _iter_datasets(ulog, "sensor_accel"):
            clip = _series(ds.data, "clip_counter", "clipping")
            if clip is None:
                continue
            finite = _finite(clip)
            if finite.size == 0:
                continue
            delta = int(max(0.0, float(finite[-1] - finite[0])))
            if delta > 0:
                clip_total += delta
                clip_topics.append(f"sensor_accel[{ds.multi_id}].clip_counter={delta}")

        if clip_total > 0:
            findings.append(
                AnomalyFinding(
                    code="vibration_clipping",
                    title="IMU 진동 클리핑 감지",
                    severity=Severity.CRITICAL,
                    detector_source="px4_firmware_gate",
                    topic="vehicle_imu_status",
                    metric="accel/gyro_clipping",
                    measured_value=float(clip_total),
                    threshold=0.0,
                    unit="counts",
                    detail=(
                        f"가속도/자이로 샘플이 ADC 포화(clipping)되었습니다. "
                        f"누적 {clip_total}회. " + "; ".join(clip_topics[:6])
                    ),
                )
            )

        vibe_peak = 0.0
        vibe_ds = _try_dataset(ulog, "estimator_status")
        if vibe_ds is not None:
            axes = []
            for axis in range(3):
                series = _indexed(vibe_ds.data, "vibe", axis)
                if series is None:
                    continue
                finite = _finite(series)
                if finite.size:
                    axes.append(float(np.max(np.abs(finite))))
            if axes:
                vibe_peak = max(axes)

        if vibe_ds is None:
            notes.append("estimator_status 토픽이 없어 vibe 피크를 계산하지 못했습니다.")
        elif vibe_peak <= 0.0:
            notes.append("estimator_status.vibe 필드가 없거나 0입니다.")
        elif vibe_peak >= VIBE_PEAK_FAIL:
            findings.append(
                AnomalyFinding(
                    code="vibration_peak",
                    title="EKF 진동 메트릭 위험 수준",
                    severity=Severity.CRITICAL,
                    detector_source="px4_firmware_gate",
                    topic="estimator_status",
                    metric="vibe_peak",
                    measured_value=round(vibe_peak, 3),
                    threshold=VIBE_PEAK_FAIL,
                    unit="m/s^2",
                    detail=(
                        f"estimator_status.vibe 피크 {vibe_peak:.2f} (Flight Review 실패 라인 "
                        f"{VIBE_PEAK_FAIL}). 소프트마운트/프로펠러 밸런스를 점검하십시오."
                    ),
                )
            )
        elif vibe_peak >= VIBE_PEAK_WARN:
            findings.append(
                AnomalyFinding(
                    code="vibration_peak",
                    title="EKF 진동 메트릭 경고",
                    severity=Severity.WARNING,
                    detector_source="px4_firmware_gate",
                    topic="estimator_status",
                    metric="vibe_peak",
                    measured_value=round(vibe_peak, 3),
                    threshold=VIBE_PEAK_WARN,
                    unit="m/s^2",
                    detail=(
                        f"estimator_status.vibe 피크 {vibe_peak:.2f} (경고 라인 {VIBE_PEAK_WARN}). "
                        "댐핑이 부족하면 EKF 게이트 초과로 이어질 수 있습니다."
                    ),
                )
            )

        return findings

    def _detect_ekf2_gates(self, ulog: ULog, notes: list[str]) -> list[AnomalyFinding]:
        findings: list[AnomalyFinding] = []
        ds = _try_dataset(ulog, "estimator_status")
        if ds is None:
            notes.append("estimator_status 토픽이 없어 EKF2 혁신 게이트를 평가하지 못했습니다.")
            return findings

        ratio_fields = (
            ("mag_test_ratio", "자기장"),
            ("vel_test_ratio", "속도"),
            ("pos_test_ratio", "위치"),
            ("hgt_test_ratio", "고도"),
            ("tas_test_ratio", "진대기속도"),
            ("hagl_test_ratio", "지면고도"),
            ("beta_test_ratio", "사이드슬립"),
        )

        found_any = False
        for field_name, label in ratio_fields:
            series = _series(ds.data, field_name)
            if series is None:
                continue
            finite = _finite(series)
            if finite.size == 0:
                continue
            found_any = True
            peak = float(np.max(finite))
            fail_ratio = float(np.mean(finite > EKF2_GATE_FAIL))
            warn_ratio = float(np.mean(finite > EKF2_GATE_WARN))

            if peak > EKF2_GATE_FAIL:
                findings.append(
                    AnomalyFinding(
                        code="ekf2_innovation_gate",
                        title=f"EKF2 {label} 혁신 게이트 초과",
                        severity=Severity.CRITICAL,
                        detector_source="px4_firmware_gate",
                        topic="estimator_status",
                        metric=field_name,
                        measured_value=round(peak, 4),
                        threshold=EKF2_GATE_FAIL,
                        unit="test_ratio",
                        sample_ratio=round(fail_ratio, 4),
                        detail=(
                            f"{field_name} 피크 {peak:.3f} > 1.0 (PX4 게이트 실패). "
                            f"전체 샘플의 {fail_ratio:.1%}가 게이트를 초과했습니다."
                        ),
                    )
                )
            elif peak > EKF2_GATE_WARN:
                findings.append(
                    AnomalyFinding(
                        code="ekf2_innovation_gate",
                        title=f"EKF2 {label} 혁신 게이트 접근",
                        severity=Severity.WARNING,
                        detector_source="px4_firmware_gate",
                        topic="estimator_status",
                        metric=field_name,
                        measured_value=round(peak, 4),
                        threshold=EKF2_GATE_WARN,
                        unit="test_ratio",
                        sample_ratio=round(warn_ratio, 4),
                        detail=(
                            f"{field_name} 피크 {peak:.3f} (경고 라인 0.5). "
                            "게이트 실패 직전 상태입니다."
                        ),
                    )
                )

        flags = _series(ds.data, "innovation_check_flags")
        if flags is not None:
            finite = _finite(flags)
            if finite.size and int(np.max(finite)) > 0:
                findings.append(
                    AnomalyFinding(
                        code="ekf2_innovation_flags",
                        title="EKF2 innovation_check_flags 설정",
                        severity=Severity.WARNING,
                        detector_source="px4_firmware_gate",
                        topic="estimator_status",
                        metric="innovation_check_flags",
                        measured_value=float(int(np.max(finite))),
                        threshold=0.0,
                        detail=(
                            f"innovation_check_flags 최대값 {int(np.max(finite))}. "
                            "하나 이상의 EKF 보조 센서 혁신 검사가 거부되었습니다."
                        ),
                    )
                )

        if not found_any:
            notes.append("estimator_status에 *_test_ratio 필드가 없습니다 (구버전 로그일 수 있음).")

        return findings

    def _detect_voltage(self, ulog: ULog, notes: list[str]) -> list[AnomalyFinding]:
        findings: list[AnomalyFinding] = []
        ds = _try_dataset(ulog, "battery_status")
        if ds is None:
            notes.append("battery_status 토픽이 없어 전압 드롭을 평가하지 못했습니다.")
            return findings

        voltage = _series(
            ds.data,
            "voltage_filtered_v",
            "voltage_v",
            "voltage_filtered",
        )
        current = _series(ds.data, "current_filtered_a", "current_a")
        remaining = _series(ds.data, "remaining")
        warning = _series(ds.data, "warning")
        timestamp = _series(ds.data, "timestamp")

        if voltage is None:
            notes.append("battery_status에 전압 필드가 없습니다.")
            return findings

        volt_raw = np.asarray(voltage, dtype=float)
        mask = np.isfinite(volt_raw)
        volt = volt_raw[mask]
        if volt.size == 0:
            return findings

        def _align(series: Optional[np.ndarray]) -> Optional[np.ndarray]:
            if series is None:
                return None
            arr = np.asarray(series, dtype=float)
            n = min(arr.size, mask.size)
            return arr[:n][mask[:n]]

        ts_aligned = _align(timestamp)
        cur_aligned = _align(current)

        vmin = float(np.min(volt))
        vmax = float(np.max(volt))
        vdrop = vmax - vmin

        n_cells = _param(ulog, "BAT_N_CELLS", "BAT1_N_CELLS")
        v_empty = _param(ulog, "BAT_V_EMPTY", "BAT1_V_EMPTY")
        low_thr = _param(ulog, "BAT_LOW_THR", "BAT1_LOW_THR")
        crit_thr = _param(ulog, "BAT_CRIT_THR", "BAT1_CRIT_THR")

        empty_pack = None
        if n_cells and v_empty:
            empty_pack = n_cells * v_empty
            if vmin <= empty_pack:
                findings.append(
                    AnomalyFinding(
                        code="voltage_empty",
                        title="팩 전압이 빈 셀 기준 이하",
                        severity=Severity.CRITICAL,
                        detector_source="log_self_params",
                        topic="battery_status",
                        metric="voltage_v",
                        measured_value=round(vmin, 3),
                        threshold=round(empty_pack, 3),
                        unit="V",
                        detail=(
                            f"최저 전압 {vmin:.2f}V ≤ BAT_N_CELLS({n_cells:.0f}) × "
                            f"BAT_V_EMPTY({v_empty:.2f}V) = {empty_pack:.2f}V."
                        ),
                    )
                )

        sag_detected = False
        if ts_aligned is not None and volt.size >= 8:
            sag_detected = self._detect_inrush_sag(
                timestamp=ts_aligned[: volt.size],
                voltage=volt,
                current=cur_aligned,
            )
        elif vdrop >= VOLTAGE_SAG_V:
            sag_detected = True

        if sag_detected:
            findings.append(
                AnomalyFinding(
                    code="voltage_drop",
                    title="부하 구간 전압 드롭 감지",
                    severity=Severity.CRITICAL if vdrop >= 1.0 else Severity.WARNING,
                    detector_source="px4_firmware_gate",
                    topic="battery_status",
                    metric="pack_voltage_sag",
                    measured_value=round(vdrop, 3),
                    threshold=VOLTAGE_SAG_V,
                    unit="V",
                    detail=(
                        f"팩 전압 범위 {vmax:.2f}V → {vmin:.2f}V (Δ {vdrop:.2f}V). "
                        "모터 인러시 또는 BEC 공유로 인한 레일 강하 가능성이 있습니다."
                    ),
                )
            )

        if remaining is not None:
            rem = _finite(remaining)
            if rem.size:
                rem_min = float(np.min(rem))
                if crit_thr is not None and rem_min <= crit_thr:
                    findings.append(
                        AnomalyFinding(
                            code="battery_critical",
                            title="배터리 remaining이 치명 임계 이하",
                            severity=Severity.CRITICAL,
                            detector_source="log_self_params",
                            topic="battery_status",
                            metric="remaining",
                            measured_value=round(rem_min, 4),
                            threshold=crit_thr,
                            detail=(
                                f"remaining 최저 {rem_min:.1%} ≤ BAT_CRIT_THR({crit_thr:.1%})."
                            ),
                        )
                    )
                elif low_thr is not None and rem_min <= low_thr:
                    findings.append(
                        AnomalyFinding(
                            code="battery_low",
                            title="배터리 remaining이 Low 임계 이하",
                            severity=Severity.WARNING,
                            detector_source="log_self_params",
                            topic="battery_status",
                            metric="remaining",
                            measured_value=round(rem_min, 4),
                            threshold=low_thr,
                            detail=(
                                f"remaining 최저 {rem_min:.1%} ≤ BAT_LOW_THR({low_thr:.1%})."
                            ),
                        )
                    )

        if warning is not None:
            warn = _finite(warning)
            if warn.size and int(np.max(warn)) >= 1:
                level = int(np.max(warn))
                findings.append(
                    AnomalyFinding(
                        code="battery_warning_flag",
                        title="battery_status.warning 플래그 활성",
                        severity=Severity.CRITICAL if level >= 2 else Severity.WARNING,
                        detector_source="px4_firmware_gate",
                        topic="battery_status",
                        metric="warning",
                        measured_value=float(level),
                        threshold=1.0,
                        detail=f"PX4 battery warning 레벨 {level} (1=low, 2=critical, 3=emergency).",
                    )
                )

        return findings

    @staticmethod
    def _detect_inrush_sag(
        timestamp: np.ndarray,
        voltage: np.ndarray,
        current: Optional[np.ndarray],
    ) -> bool:
        """0.3초 창의 롤링 최댓값 대비 전압 강하를 벡터 연산으로 판정한다."""

        n = min(timestamp.size, voltage.size)
        if current is not None:
            n = min(n, current.size)
        if n < 8:
            return False

        t = timestamp[:n].astype(float)
        v = voltage[:n]
        dt = float(np.median(np.diff(t))) if n > 1 else 3.0e5
        win = max(2, int(round(3.0e5 / max(dt, 1.0))))
        if win >= n:
            return bool((float(np.max(v)) - float(np.min(v))) >= VOLTAGE_SAG_V)

        roll_v = np.max(np.lib.stride_tricks.sliding_window_view(v, win), axis=1)
        drop = roll_v - v[win - 1 :]
        sag_idx = drop >= VOLTAGE_SAG_V
        if not np.any(sag_idx):
            return False
        if current is None:
            return True
        c = current[:n]
        roll_c = np.min(np.lib.stride_tricks.sliding_window_view(c, win), axis=1)
        inrush = c[win - 1 :] - roll_c
        return bool(np.any(sag_idx & (inrush >= 0.5)))

    def _detect_failsafe_flags(self, ulog: ULog) -> list[AnomalyFinding]:
        findings: list[AnomalyFinding] = []
        ds = _try_dataset(ulog, "vehicle_status")
        if ds is None:
            return findings
        failsafe = _series(ds.data, "failsafe")
        if failsafe is None:
            return findings
        finite = _finite(failsafe)
        if finite.size and int(np.max(finite)) >= 1:
            findings.append(
                AnomalyFinding(
                    code="vehicle_failsafe",
                    title="비행 중 Failsafe 플래그 활성",
                    severity=Severity.CRITICAL,
                    detector_source="px4_firmware_gate",
                    topic="vehicle_status",
                    metric="failsafe",
                    measured_value=float(int(np.max(finite))),
                    threshold=1.0,
                    detail="vehicle_status.failsafe가 1 이상으로 올라갔습니다. RC/배터리/EKF 페일세이프 로그를 확인하십시오.",
                )
            )
        return findings

    def _compare_canonical_params(
        self, ulog: ULog, catalog: CanonicalCatalog
    ) -> list[ParamDelta]:
        deltas: list[ParamDelta] = []
        log_params = ulog.initial_parameters or {}
        seen: set[str] = set()

        for param in catalog.params.values():
            names = (param.name, *param.aliases)
            log_value: Optional[float] = None
            matched_name = param.name
            for name in names:
                if name in log_params:
                    try:
                        log_value = float(log_params[name])
                        matched_name = name
                    except (TypeError, ValueError):
                        log_value = None
                    break
            if param.name in seen:
                continue
            seen.add(param.name)
            matches = False
            if log_value is not None:
                matches = math.isclose(log_value, param.value, rel_tol=0.0, abs_tol=1e-3)
            deltas.append(
                ParamDelta(
                    param_name=matched_name,
                    log_value=log_value,
                    canonical_value=param.value,
                    unit=param.unit,
                    matches=matches,
                    canonical_id=param.source_id,
                    canonical_source=param.source_file,
                )
            )
        return deltas

    def _build_prescriptions(
        self,
        ulog: ULog,
        catalog: CanonicalCatalog,
        findings: list[AnomalyFinding],
        deltas: list[ParamDelta],
    ) -> list[ParameterPrescription]:
        prescriptions: list[ParameterPrescription] = []
        codes = {f.code for f in findings}

        for delta in deltas:
            if delta.matches:
                continue
            reason = (
                f"로그 값 {delta.log_value} ≠ Canonical {delta.canonical_value}"
                if delta.log_value is not None
                else f"로그에 {delta.param_name}이(가) 없어 Canonical 권고값 {delta.canonical_value}을(를) 적용하십시오."
            )
            if delta.param_name in {"NAV_RCL_ACT"}:
                reason = (
                    "RC 손실 페일세이프를 Canonical 표준인 RTL(NAV_RCL_ACT=2)로 맞추십시오. "
                    + reason
                )
            if delta.param_name in {"RTL_RETURN_ALT", "RTL_ALT"}:
                reason = (
                    f"최소 RTL 고도를 Canonical 표준 {delta.canonical_value:.0f}m 이상으로 설정하십시오. "
                    + reason
                )
            if delta.param_name == "EKF2_HGT_REF":
                reason = (
                    "실내/기압 드리프트 환경에서는 Canonical 표준대로 "
                    "EKF2_HGT_REF=2(Range sensor)를 사용하십시오. "
                    + reason
                )
            prescriptions.append(
                ParameterPrescription(
                    kind="px4_param",
                    param_name=delta.param_name,
                    current_value=delta.log_value,
                    prescribed_value=delta.canonical_value,
                    unit=delta.unit,
                    reason=reason,
                    canonical_id=delta.canonical_id,
                    canonical_source=delta.canonical_source,
                )
            )

        hgt_issue = any(
            f.code == "ekf2_innovation_gate" and f.metric == "hgt_test_ratio"
            for f in findings
        )
        hgt_param = catalog.get("EKF2_HGT_REF")
        current_hgt = _param(ulog, "EKF2_HGT_REF")
        already = {p.param_name for p in prescriptions}
        if hgt_issue and hgt_param and "EKF2_HGT_REF" not in already:
            if current_hgt is None or not math.isclose(current_hgt, hgt_param.value, abs_tol=1e-3):
                prescriptions.append(
                    ParameterPrescription(
                        kind="px4_param",
                        param_name="EKF2_HGT_REF",
                        current_value=current_hgt,
                        prescribed_value=hgt_param.value,
                        reason=(
                            "고도 혁신 게이트가 초과되었습니다. Canonical 실내 표준은 "
                            "EKF2_HGT_REF=2(Range sensor)로 기압 고도 드리프트를 차단합니다."
                        ),
                        canonical_id=hgt_param.source_id,
                        canonical_source=hgt_param.source_file,
                    )
                )

        if codes & {"voltage_drop", "voltage_empty", "battery_critical", "battery_warning_flag"}:
            if catalog.hardware:
                hw = catalog.hardware[0]
                prescriptions.append(
                    ParameterPrescription(
                        kind="hardware",
                        param_name=None,
                        reason=hw.text,
                        canonical_id=hw.source_id,
                        canonical_source=hw.source_file,
                    )
                )
            else:
                prescriptions.append(
                    ParameterPrescription(
                        kind="needs_canonical_review",
                        reason=(
                            "전압 드롭이 감지되었으나 Canonical SSOT에 배터리/BEC 처방값이 없습니다. "
                            "인간 검토 후 02_Canonical 등재가 필요합니다."
                        ),
                    )
                )

        if codes & {"vibration_clipping", "vibration_peak"}:
            imu_cut = catalog.get("IMU_GYRO_CUTOFF") or catalog.get("IMU_DGYRO_CUTOFF")
            if imu_cut:
                prescriptions.append(
                    ParameterPrescription(
                        kind="px4_param",
                        param_name=imu_cut.name,
                        current_value=_param(ulog, imu_cut.name),
                        prescribed_value=imu_cut.value,
                        unit="Hz",
                        reason="진동 이상에 대한 Canonical IMU 필터 컷오프 처방입니다.",
                        canonical_id=imu_cut.source_id,
                        canonical_source=imu_cut.source_file,
                    )
                )
            else:
                prescriptions.append(
                    ParameterPrescription(
                        kind="needs_canonical_review",
                        param_name="IMU_GYRO_CUTOFF",
                        current_value=_param(ulog, "IMU_GYRO_CUTOFF"),
                        reason=(
                            "진동 클리핑/피크가 감지되었습니다. Canonical SSOT에 "
                            "IMU_GYRO_CUTOFF·IMU_DGYRO_CUTOFF·소프트마운트 처방값이 없어 "
                            "수치를 발명하지 않습니다. 프로펠러 밸런스와 댐핑을 점검하고 "
                            "검증된 컷오프를 Canonical에 등재하십시오."
                        ),
                    )
                )

        if "ekf2_innovation_gate" in codes and not hgt_issue:
            # 고도가 아닌 mag/vel/pos 게이트: Canonical에 해당 튜닝이 있을 때만 처방
            related = [
                catalog.get(name)
                for name in ("EKF2_MAG_GATE", "EKF2_VEL_GATE", "EKF2_POS_GATE")
            ]
            if not any(related) and not any(
                p.kind == "needs_canonical_review" and p.param_name is None
                for p in prescriptions
            ):
                if not any(
                    f.metric in {"hgt_test_ratio"} for f in findings
                ):
                    prescriptions.append(
                        ParameterPrescription(
                            kind="needs_canonical_review",
                            reason=(
                                "EKF2 혁신 게이트 초과가 감지되었습니다. Canonical SSOT에 "
                                "EKF2_*_GATE / 노이즈 처방값이 없어 수치 튜닝을 제시하지 않습니다. "
                                "GPS 가림, 자기장 간섭, 진동을 먼저 제거하고 Canonical 등재를 진행하십시오."
                            ),
                        )
                    )

        # 중복 제거 (같은 param_name + kind)
        unique: list[ParameterPrescription] = []
        seen_keys: set[tuple[Any, ...]] = set()
        for item in prescriptions:
            key = (item.kind, item.param_name, item.prescribed_value, item.reason[:40])
            if key in seen_keys:
                continue
            seen_keys.add(key)
            unique.append(item)

        return unique

    def _collect_logged_events(self, ulog: ULog, limit: int = 20) -> list[str]:
        events: list[str] = []
        for msg in ulog.logged_messages or []:
            text = (msg.message or "").strip()
            if not text:
                continue
            lowered = text.lower()
            if any(hint in lowered for hint in _EVENT_HINTS):
                events.append(text)
            if len(events) >= limit:
                break
        return events

    def _write_discovery_report(
        self, report: AnalysisReport, catalog: CanonicalCatalog
    ) -> str:
        """분석 산출물은 인간 검토 전 단계이므로 03_Discovery / needs_review 로만 저장한다."""

        self.discovery_dir.mkdir(parents=True, exist_ok=True)
        path = self.discovery_dir / f"{report.report_id}.md"
        wiki_names = list(dict.fromkeys(["Index", "SCHEMA", *catalog.source_docs]))
        wiki_links = " ".join(f"[[{name}]]" for name in wiki_names)
        findings_md = (
            "\n".join(
                f"- **[{f.severity.value}] {f.title}** (`{f.code}`): {f.detail}"
                for f in report.findings
            )
            or "- 탐지된 이상 없음"
        )
        rx_md = (
            "\n".join(
                (
                    f"- **{p.param_name or p.kind}**: "
                    f"{'' if p.current_value is None else f'현재 {p.current_value} → '}"
                    f"{'' if p.prescribed_value is None else f'처방 {p.prescribed_value} '}"
                    f"— {p.reason}"
                    + (f" (출처 [[{p.canonical_source}]])" if p.canonical_source else "")
                )
                for p in report.prescriptions
            )
            or "- Canonical 대비 추가 처방 없음"
        )
        delta_md = (
            "\n".join(
                f"- `{d.param_name}`: 로그 {d.log_value} / Canonical {d.canonical_value} "
                f"({'일치' if d.matches else '불일치'}) — [[{d.canonical_source}]]"
                for d in report.canonical_deltas
            )
            or "- Canonical에서 추출된 PX4 파라미터가 없습니다."
        )
        events_md = (
            "\n".join(f"- {e}" for e in report.logged_events) or "- 관련 로그 메시지 없음"
        )
        notes_md = "\n".join(f"- {n}" for n in report.notes) or "- 없음"

        md = f"""---
id: {report.report_id}
title: ULog 비행 로그 이상 진단 리포트 ({report.summary.filename})
status: needs_review
reviewed: false
category: 06_Troubleshooting
decision: pending
tags: [ulog, px4, diagnostics, ekf2, vibration, battery]
---

# ULog 비행 로그 이상 진단 리포트

- 상위 인덱스: [[Index]]
- Canonical 대조 문서: {wiki_links}
- 종합 심각도: **{report.overall_severity.value}**
- 원본 파일: `{report.summary.filename}`
- 비행 시간: {report.summary.duration_s}s
- 펌웨어: {report.summary.firmware or "unknown"}
- 보드: {report.summary.board or "unknown"}

## 탐지된 이상

{findings_md}

## Canonical 파라미터 처방

{rx_md}

## 로그 파라미터 vs Canonical

{delta_md}

## 관련 로그 메시지

{events_md}

## 분석 노트

{notes_md}

> 이 문서는 에이전트 자동 산출물이며 `status: needs_review` 입니다.
> 수치 처방은 `02_Canonical` SSOT만 사용했고, Canonical에 없는 튜닝값은 발명하지 않았습니다.
"""
        path.write_text(md, encoding="utf-8")
        return str(path.relative_to(self.repo_root))


def analyze_ulog_file(
    ulog_path: str | Path,
    original_filename: str | None = None,
    save_report: bool = True,
) -> AnalysisReport:
    """모듈 레벨 진입점. FastAPI 및 CLI에서 동일하게 사용한다."""

    return ULogAnalyzer().analyze(
        ulog_path,
        original_filename=original_filename,
        save_report=save_report,
    )


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="PX4 ULog 이상 진단 엔진")
    parser.add_argument("ulog", help="분석할 .ulg 파일 경로")
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="03_Discovery 마크다운 리포트를 저장하지 않음",
    )
    args = parser.parse_args()

    result = analyze_ulog_file(args.ulog, save_report=not args.no_save)
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
