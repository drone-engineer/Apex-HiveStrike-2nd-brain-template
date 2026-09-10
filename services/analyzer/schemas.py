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


class AnalysisReport(BaseModel):
    """비행 로그 이상 진단 및 Canonical 처방 리포트."""

    report_id: str
    overall_severity: Severity
    summary: FlightSummary
    findings: list[AnomalyFinding] = Field(default_factory=list)
    prescriptions: list[ParameterPrescription] = Field(default_factory=list)
    canonical_deltas: list[ParamDelta] = Field(default_factory=list)
    logged_events: list[str] = Field(default_factory=list)
    canonical_docs_used: list[str] = Field(default_factory=list)
    discovery_path: Optional[str] = None
    notes: list[str] = Field(default_factory=list)
