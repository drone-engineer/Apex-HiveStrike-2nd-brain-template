"""ULog 이상 진단 엔진의 Pydantic v2 응답 스키마."""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Severity(str, Enum):
    """진단 항목의 심각도. overall_severity 집계에도 사용한다."""

    OK = "ok"
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AnomalyFinding(BaseModel):
    """단일 이상 탐지 결과.

    detector_source는 탐지 게이트의 출처다.
    PX4 펌웨어가 test_ratio>1.0을 게이트 실패로 정의하는 것처럼,
    탐지 기준과 Canonical 처방값은 출처를 분리한다.
    """

    code: str = Field(..., description="이상 코드 (vibration_clipping, ekf2_gate, voltage_drop 등)")
    title: str
    severity: Severity
    detector_source: Literal["px4_firmware_gate", "log_self_params", "canonical_ssot"]
    topic: Optional[str] = None
    metric: Optional[str] = None
    measured_value: Optional[float] = None
    threshold: Optional[float] = None
    unit: Optional[str] = None
    detail: str
    sample_ratio: Optional[float] = Field(
        default=None,
        description="전체 샘플 중 임계값을 초과한 비율 (0.0~1.0)",
    )
    t_s: Optional[float] = Field(default=None, description="이상 시각(로그 시작 기준 초)")


class TopicProfile(BaseModel):
    """ULog에 실제로 기록된 토픽 1개의 샘플 통계."""

    name: str
    instance: int = 0
    samples: int
    rate_hz: Optional[float] = None
    duration_s: Optional[float] = None
    fields: list[str] = Field(default_factory=list)


class MetricStats(BaseModel):
    """주요 시계열의 요약 통계. 처방값이 아니라 관측값이다."""

    name: str
    topic: str
    unit: Optional[str] = None
    samples: int
    min: float
    max: float
    mean: float
    std: float
    p95: float


class TimelineEvent(BaseModel):
    """모드 전환·페일세이프·로그 메시지 타임라인."""

    t_s: float
    kind: Literal["mode", "arming", "failsafe", "log", "dropout"]
    text: str
    severity: Severity = Severity.INFO


class FlightKinematics(BaseModel):
    """위치/속도에서 뽑은 비행 규모. GPS가 없으면 로컬 NED만 사용한다."""

    armed_s: Optional[float] = None
    distance_m: Optional[float] = None
    max_speed_mps: Optional[float] = None
    max_abs_vz_mps: Optional[float] = None
    alt_min_m: Optional[float] = None
    alt_max_m: Optional[float] = None
    alt_range_m: Optional[float] = None


class FlightSummary(BaseModel):
    """ULog 헤더/메타에서 추출한 비행 개요."""

    filename: str
    duration_s: float
    firmware: Optional[str] = None
    board: Optional[str] = None
    start_timestamp_us: int
    topic_count: int
    parameter_count: int
    available_topics: list[str] = Field(default_factory=list)
    logged_event_count: int = 0
    dropout_count: int = 0
    file_size_bytes: Optional[int] = None
    kinematics: Optional[FlightKinematics] = None


class ParameterPrescription(BaseModel):
    """Canonical SSOT와 대조한 파라미터/하드웨어 처방.

    kind=needs_canonical_review 인 항목은 수치 처방을 하지 않는다.
    AGENTS.md: 튜닝 수치는 02_Canonical만 진실로 채택한다.
    """

    kind: Literal["px4_param", "hardware", "needs_canonical_review"]
    param_name: Optional[str] = None
    current_value: Optional[float] = None
    prescribed_value: Optional[float] = None
    unit: Optional[str] = None
    reason: str
    canonical_id: Optional[str] = None
    canonical_source: Optional[str] = Field(
        default=None,
        description="옵시디언 위키링크용 파일명 (확장자 제외)",
    )


class ParamDelta(BaseModel):
    """로그에 기록된 현재 파라미터와 Canonical 권고값의 차이."""

    param_name: str
    log_value: Optional[float] = None
    canonical_value: float
    unit: Optional[str] = None
    matches: bool
    canonical_id: Optional[str] = None
    canonical_source: Optional[str] = None


class RiskItem(BaseModel):
    """로그에서 예상되는 문제와 다음 비행 전 정비 항목.

    수치 처방은 Canonical에 있을 때만 canonical_actions에 넣는다.
    Canonical이 없으면 ssot_gap에 공백을 적고 숫자를 발명하지 않는다.
    """

    id: str
    problem: str
    severity: Severity
    likelihood: Literal["observed", "likely", "possible"]
    impact: str
    evidence_codes: list[str] = Field(default_factory=list)
    inspect_now: list[str] = Field(default_factory=list)
    canonical_actions: list[str] = Field(default_factory=list)
    ssot_gap: Optional[str] = None


class ChartSeries(BaseModel):
    """대시보드 Plotly용 다운샘플 시계열. 원본 ULog 전체 샘플은 넣지 않는다."""

    id: str
    title: str
    x_label: str
    y_label: str
    kind: Literal["line", "path"] = "line"
    x: list[float] = Field(default_factory=list)
    y: list[float] = Field(default_factory=list)
    y2: Optional[list[float]] = None


class AnalysisReport(BaseModel):
    """비행 로그 종합 진단 및 Canonical 처방 리포트."""

    report_id: str
    overall_severity: Severity
    executive_summary: list[str] = Field(default_factory=list)
    summary: FlightSummary
    findings: list[AnomalyFinding] = Field(default_factory=list)
    risks: list[RiskItem] = Field(default_factory=list)
    prescriptions: list[ParameterPrescription] = Field(default_factory=list)
    canonical_deltas: list[ParamDelta] = Field(default_factory=list)
    logged_events: list[str] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    topic_profiles: list[TopicProfile] = Field(default_factory=list)
    metric_stats: list[MetricStats] = Field(default_factory=list)
    canonical_docs_used: list[str] = Field(default_factory=list)
    discovery_path: Optional[str] = None
    pdf_path: Optional[str] = None
    notes: list[str] = Field(default_factory=list)
    charts: list[ChartSeries] = Field(default_factory=list)
