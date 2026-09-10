"""로그 이상 → 예상 문제·대응 정비 플레이북.

수치 처방은 Canonical 카탈로그에 있을 때만 붙인다.
점검 문장은 하드웨어/운용 절차이며 컷오프·게이트 Hz를 발명하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

from services.analyzer.full_scan import (
    CPU_LOAD_WARN,
    EPH_WARN_M,
    RAM_WARN,
    RC_RSSI_WARN,
    SAT_WARN,
    TEMP_WARN_C,
)
from services.analyzer.schemas import (
    AnomalyFinding,
    MetricStats,
    ParameterPrescription,
    RiskItem,
    Severity,
)


class _ParamLike(Protocol):
    name: str
    value: float
    source_file: str
    unit: Optional[str]


class _HwLike(Protocol):
    topic: str
    text: str
    source_file: str


class _CatalogLike(Protocol):
    hardware: list[_HwLike]

    def get(self, name: str) -> Optional[_ParamLike]: ...


NEAR_MISS_RATIO = 0.80


@dataclass(frozen=True)
class _Family:
    id: str
    problem: str
    impact: str
    inspect_now: tuple[str, ...]
    prefixes: tuple[str, ...]
    exact: tuple[str, ...] = ()
    canonical_params: tuple[str, ...] = ()
    hardware_topics: tuple[str, ...] = ()
    ssot_gap: Optional[str] = None


_FAMILIES: tuple[_Family, ...] = (
    _Family(
        id="gnss",
        problem="GNSS 품질 저하로 위치제어·미션·RTL이 깨질 수 있습니다.",
        impact="3D 픽스 손실 시 POSCTL/AUTO가 실패하고, RC까지 없으면 귀환 경로를 잡지 못할 수 있습니다.",
        inspect_now=(
            "안테나 커넥터·케이블 장력·기체 차폐를 점검하십시오.",
            "이륙 전 야외에서 3D 픽스와 위성 수를 확인하십시오.",
            "도심·탄소 프레임 근처 멀티패스와 재밍 환경을 피하십시오.",
        ),
        prefixes=("gps_",),
        canonical_params=("NAV_RCL_ACT", "RTL_RETURN_ALT", "RTL_ALT"),
        ssot_gap="GNSS 최소 위성·eph 한도가 Canonical 런북에 없습니다. 인간 검토 후 06_Runbooks 승격이 필요합니다.",
    ),
    _Family(
        id="rc_link",
        problem="RC 또는 GCS 링크 손실로 페일세이프가 개입할 수 있습니다.",
        impact="링크가 끊기면 설정된 NAV_RCL_ACT에 따라 착륙·홀드·RTL이 갈리며, 표준과 다르면 예상과 다른 기동이 납니다.",
        inspect_now=(
            "송신기·수신기 안테나 방향과 페이드를 점검하십시오.",
            "텔레메트리 안테나 이격과 접지를 확인하십시오.",
            "다음 비행 전 RC 손실 동작을 지상에서 재현 점검하십시오.",
        ),
        prefixes=("rc_", "status_rc_", "status_data_link_"),
        exact=("status_rc_signal_lost", "status_data_link_lost"),
        canonical_params=("NAV_RCL_ACT", "RTL_RETURN_ALT", "RTL_ALT"),
        ssot_gap="RC RSSI 하한이 Canonical에 없습니다. 페일세이프 수치는 Canonical 값만 적용합니다.",
    ),
    _Family(
        id="compute_log",
        problem="FC CPU/RAM 부하와 로그 드롭아웃으로 다음 비행의 재현·튜닝이 어려워질 수 있습니다.",
        impact="드롭아웃이 커지면 사고 구간 시계열이 비고, 부하가 더 오르면 제어 지연이 겹칠 수 있습니다.",
        inspect_now=(
            "SD카드 상태·속도 등급·남은 용량을 점검하십시오.",
            "불필요한 고속 로깅 토픽을 줄일지 검토하십시오. (Hz 수치는 Canonical에 없으면 제시하지 않습니다.)",
            "동시 실행 모듈(OSD, 외부 비전) 부하를 확인하십시오.",
        ),
        prefixes=("cpu_", "ram_", "ulog_", "logging_"),
        exact=("cpu_load_high", "ram_usage_high", "ulog_dropout", "logging_gap"),
        ssot_gap="CPU/로깅 한도와 SD 교체 기준이 Canonical 런북에 없습니다.",
    ),
    _Family(
        id="actuator",
        problem="액추에이터 PWM 포화로 자세 추종 실패·모터 과열이 예상됩니다.",
        impact="포화가 반복되면 풍속·기동에서 여유 추력이 없고, ESC/모터 수명이 짧아집니다.",
        inspect_now=(
            "프로펠러 손상·밸런스·피치를 점검하십시오.",
            "CG와 페이로드가 믹서 가정과 맞는지 확인하십시오.",
            "바람·고고도에서 호버 쓰로틀이 과도하지 않은지 지상 호버로 확인하십시오.",
        ),
        prefixes=("actuator_",),
        ssot_gap="호버 쓰로틀·최대 틸트 Canonical 한도가 없어 수치 튜닝은 제시하지 않습니다.",
    ),
    _Family(
        id="battery",
        problem="전압 강하·저잔량으로 SBC 리셋 또는 저전압 페일세이프가 예상됩니다.",
        impact="모터 급기동 인러시가 컴패니언/FC를 리셋하면 공중 재시동 없이 추락할 수 있습니다.",
        inspect_now=(
            "배터리 내부저항·커넥터 발열·케이블 굵기를 점검하십시오.",
            "다음 비행 전 잔량·셀 밸런스를 확인하십시오.",
        ),
        prefixes=("voltage_", "battery_"),
        canonical_params=("BAT_LOW_THR", "BAT_CRIT_THR", "BAT_EMERGEN_THR"),
        hardware_topics=("bec", "power", "sbc", "battery"),
        ssot_gap="배터리 잔량 임계값이 Canonical에 없으면 로그의 BAT_*만 관측 근거로 씁니다.",
    ),
    _Family(
        id="vibration",
        problem="진동 클리핑/피크로 IMU 신뢰도가 떨어져 자세·고도 추정이 흔들릴 수 있습니다.",
        impact="클리핑이 반복되면 EKF가 가속도를 버리고, 호버 발진이나 고도 점프가 날 수 있습니다.",
        inspect_now=(
            "프로펠러 밸런스·모터 베어링·소프트마운트 마모를 점검하십시오.",
            "랜딩기어·페이로드 공진이 IMU 축과 겹치는지 확인하십시오.",
        ),
        prefixes=("vibration_",),
        canonical_params=("IMU_GYRO_CUTOFF", "IMU_DGYRO_CUTOFF"),
        ssot_gap="IMU_GYRO_CUTOFF·IMU_DGYRO_CUTOFF Canonical 처방값이 없어 필터 Hz를 발명하지 않습니다. 검증 후 Canonical 등재가 필요합니다.",
    ),
    _Family(
        id="ekf2",
        problem="EKF2 혁신 게이트/폴트로 위치·고도 추정이 발산할 수 있습니다.",
        impact="게이트 실패가 이어지면 홀드/미션이 불안정하고, 고도 소스가 기압이면 실내에서 드리프트가 커집니다.",
        inspect_now=(
            "GPS 가림, 자기장(배터리·ESC 근접), 진동을 먼저 제거하십시오.",
            "실내라면 거리센서 장착과 고도 소스 전환 여부를 확인하십시오.",
        ),
        prefixes=("ekf2_", "ekf_"),
        canonical_params=("EKF2_HGT_REF", "EKF2_MAG_GATE", "EKF2_VEL_GATE", "EKF2_POS_GATE"),
        ssot_gap="EKF2_*_GATE / 노이즈 Canonical 값이 없으면 수치 튜닝을 제시하지 않습니다.",
    ),
    _Family(
        id="thermal",
        problem="IMU/센서 온도 상승으로 바이어스 드리프트가 커질 수 있습니다.",
        impact="고온에서 자이로 바이어스가 변하면 호버 중 슬로우 드리프트가 납니다.",
        inspect_now=(
            "FC 통풍·햇빛 노출·소프트마운트 밀폐를 점검하십시오.",
            "장시간 지상 대기 후 IMU 온도가 안정된 뒤에 시동하십시오.",
        ),
        prefixes=("imu_temperature",),
        ssot_gap="IMU 온도 한도가 Canonical에 없습니다.",
    ),
    _Family(
        id="failsafe_misc",
        problem="기체 페일세이프·지오펜스·미션 실패 플래그가 올라 다음 비행에서 조기 중단될 수 있습니다.",
        impact="원인 미해결 시 이륙 직후 강제 착륙/홀드가 반복됩니다.",
        inspect_now=(
            "지오펜스·미션 웨이포인트·모터 상태를 QGC/로그 메시지와 대조하십시오.",
            "직전 페일세이프 원인을 해소하기 전에 AUTO로 올리지 마십시오.",
        ),
        prefixes=("vehicle_failsafe", "status_engine_", "status_mission_", "status_geofence_"),
        canonical_params=("NAV_RCL_ACT", "RTL_RETURN_ALT"),
        ssot_gap="지오펜스/미션 실패 런북이 Canonical 06_Runbooks에 없습니다.",
    ),
)


def build_risks(
    findings: list[AnomalyFinding],
    stats: list[MetricStats],
    prescriptions: list[ParameterPrescription],
    catalog: _CatalogLike,
) -> list[RiskItem]:
    """finding + 니어미스 통계를 예상 문제 목록으로 접는다."""

    risks: list[RiskItem] = []
    used_codes: set[str] = set()

    for family in _FAMILIES:
        matched = [f for f in findings if _matches(family, f.code)]
        if not matched:
            continue
        used_codes.update(f.code for f in matched)
        risks.append(_from_findings(family, matched, prescriptions, catalog))

    for leftover in findings:
        if leftover.code in used_codes:
            continue
        used_codes.add(leftover.code)
        risks.append(
            RiskItem(
                id=leftover.code,
                problem=leftover.title,
                severity=leftover.severity,
                likelihood="observed",
                impact=leftover.detail,
                evidence_codes=[leftover.code],
                inspect_now=["해당 토픽과 타임라인을 재확인하고 재현 조건을 기록하십시오."],
                canonical_actions=[],
                ssot_gap="이 코드에 대한 Canonical 런북이 없습니다.",
            )
        )

    for near in _near_misses(stats, used_codes):
        risks.append(near)

    order = {"observed": 0, "likely": 1, "possible": 2}
    sev_order = {Severity.CRITICAL: 0, Severity.WARNING: 1, Severity.INFO: 2, Severity.OK: 3}
    risks.sort(key=lambda r: (order.get(r.likelihood, 9), sev_order.get(r.severity, 9), r.id))
    return risks


def _matches(family: _Family, code: str) -> bool:
    if code in family.exact:
        return True
    return any(code.startswith(prefix) for prefix in family.prefixes)


def _from_findings(
    family: _Family,
    matched: list[AnomalyFinding],
    prescriptions: list[ParameterPrescription],
    catalog: _CatalogLike,
) -> RiskItem:
    codes = [f.code for f in matched]
    severity = max((f.severity for f in matched), key=_sev_rank)
    evidence = "; ".join(dict.fromkeys(f.title for f in matched))
    canonical = _canonical_actions(family, catalog)
    for rx in prescriptions:
        if rx.kind == "px4_param" and rx.param_name in family.canonical_params:
            if any((rx.param_name or "") in line for line in canonical):
                continue
            line = f"{rx.param_name}={rx.prescribed_value}"
            if rx.canonical_source:
                line += f" (출처 {rx.canonical_source})"
            canonical.append(line)
        elif rx.kind == "hardware" and family.hardware_topics:
            if any(rx.reason[:24] in line for line in canonical):
                continue
            src = f" (출처 {rx.canonical_source})" if rx.canonical_source else ""
            canonical.append(f"{rx.reason}{src}")
    canonical = list(dict.fromkeys(canonical))
    return RiskItem(
        id=family.id,
        problem=family.problem,
        severity=severity,
        likelihood="observed",
        impact=f"{family.impact} 근거: {evidence}.",
        evidence_codes=codes,
        inspect_now=list(family.inspect_now),
        canonical_actions=canonical,
        ssot_gap=family.ssot_gap,
    )


def _canonical_actions(family: _Family, catalog: _CatalogLike) -> list[str]:
    actions: list[str] = []
    for name in family.canonical_params:
        param = catalog.get(name)
        if param is None:
            continue
        unit = f" {param.unit}" if param.unit else ""
        actions.append(f"{param.name}={param.value}{unit} (출처 {param.source_file})")
    wanted = {t.lower() for t in family.hardware_topics}
    if not wanted:
        return actions
    for hw in catalog.hardware:
        blob = f"{hw.topic} {hw.text}".lower()
        if not any(token in blob for token in wanted):
            continue
        actions.append(f"{hw.text} (출처 {hw.source_file})")
    return actions


def _near_misses(stats: list[MetricStats], used_codes: set[str]) -> list[RiskItem]:
    items: list[RiskItem] = []
    by_name = {s.name: s for s in stats}

    def add(
        risk_id: str,
        problem: str,
        impact: str,
        inspect: list[str],
        gap: str,
        skip_if: set[str],
    ) -> None:
        if skip_if & used_codes:
            return
        items.append(
            RiskItem(
                id=risk_id,
                problem=problem,
                severity=Severity.INFO,
                likelihood="possible",
                impact=impact,
                evidence_codes=[],
                inspect_now=inspect,
                canonical_actions=[],
                ssot_gap=gap,
            )
        )

    sats = by_name.get("gps_satellites")
    if sats is not None:
        # 경고선 8 바로 위(9~10)는 아직 finding이 아니지만 다음 비행에서 깨질 수 있다.
        hi = SAT_WARN / NEAR_MISS_RATIO
        if SAT_WARN < sats.min <= hi:
            add(
                "gnss_near_miss",
                "GNSS 위성 수가 경고선에 가깝습니다.",
                f"satellites_used 최저 {sats.min:.0f} (경고선 {SAT_WARN}). 차폐·자세에서 픽스 손실이 날 수 있습니다.",
                ["이륙 전 위성 수와 eph를 확인하고 안테나 시야를 확보하십시오."],
                "GNSS 최소 위성 Canonical 런북이 없습니다.",
                {"gps_low_satellites", "gps_no_3d_fix", "gps_fix_drop"},
            )

    eph = by_name.get("gps_eph")
    if eph is not None and (EPH_WARN_M * NEAR_MISS_RATIO) <= eph.max < EPH_WARN_M:
        add(
            "gnss_eph_near_miss",
            "GNSS 수평 오차가 경고선에 접근 중입니다.",
            f"eph 피크 {eph.max:.2f} m (경고선 {EPH_WARN_M} m).",
            ["멀티패스·안테나 각도를 점검하십시오."],
            "eph 한도가 Canonical에 없습니다.",
            {"gps_high_eph"},
        )

    cpu = by_name.get("cpu_load")
    if cpu is not None and (CPU_LOAD_WARN * NEAR_MISS_RATIO) <= cpu.max < CPU_LOAD_WARN:
        add(
            "cpu_near_miss",
            "FC CPU 부하가 경고선에 가깝습니다.",
            f"cpuload.load 피크 {cpu.max:.1%} (경고선 {CPU_LOAD_WARN:.0%}). 로깅을 늘리면 드롭아웃이 날 수 있습니다.",
            ["SD카드와 동시 실행 모듈 부하를 점검하십시오."],
            "CPU 한도 Canonical 런북이 없습니다.",
            {"cpu_load_high"},
        )

    ram = by_name.get("ram_usage")
    if ram is not None and (RAM_WARN * NEAR_MISS_RATIO) <= ram.max < RAM_WARN:
        add(
            "ram_near_miss",
            "FC RAM 사용량이 경고선에 가깝습니다.",
            f"ram_usage 피크 {ram.max:.1%} (경고선 {RAM_WARN:.0%}).",
            ["불필요 모듈을 끄고 다음 비행 로그 용량을 줄이십시오."],
            "RAM 한도 Canonical 런북이 없습니다.",
            {"ram_usage_high"},
        )

    rssi = by_name.get("rc_rssi")
    if rssi is not None:
        scale = RC_RSSI_WARN if rssi.min <= 100 else 50.0
        if 0 < rssi.min and scale <= rssi.min <= scale / NEAR_MISS_RATIO:
            add(
                "rc_rssi_near_miss",
                "RC RSSI가 경고선 근처입니다.",
                f"RSSI 최저 {rssi.min:.1f} (경고 관측선 {scale}). 자세·거리에 따라 링크 손실이 날 수 있습니다.",
                ["안테나 방향과 기체 차폐를 점검하십시오."],
                "RSSI 하한이 Canonical에 없습니다.",
                {"rc_low_rssi", "rc_lost", "status_rc_signal_lost"},
            )

    temp = by_name.get("imu_temp") or by_name.get("accel_temp")
    if temp is not None and (TEMP_WARN_C * NEAR_MISS_RATIO) <= temp.max < TEMP_WARN_C:
        add(
            "imu_temp_near_miss",
            "IMU 온도가 경고선에 접근 중입니다.",
            f"온도 피크 {temp.max:.1f}C (경고선 {TEMP_WARN_C}C). 장시간 대기 후 바이어스 드리프트가 커질 수 있습니다.",
            ["통풍과 직사광선을 점검하고 온도 안정 후 시동하십시오."],
            "IMU 온도 Canonical 한도가 없습니다.",
            {"imu_temperature_high"},
        )

    return items


def _sev_rank(severity: Severity) -> int:
    return {
        Severity.OK: 0,
        Severity.INFO: 1,
        Severity.WARNING: 2,
        Severity.CRITICAL: 3,
    }[severity]
