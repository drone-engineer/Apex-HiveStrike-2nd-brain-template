"""ULog 전 토픽 스캔: 통계·타임라인·GPS/RC/CPU/포화/드롭아웃.

탐지 게이트는 PX4 메시지 정의와 로그 자체 파라미터만 사용한다.
튜닝 수치 처방은 이 모듈에서 하지 않는다.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
from pyulog import ULog

from services.analyzer.schemas import (
    AnomalyFinding,
    ChartSeries,
    FlightKinematics,
    MetricStats,
    Severity,
    TimelineEvent,
    TopicProfile,
)
from services.analyzer.ulog_analyzer import (
    _downsample_xy,
    _finite,
    _indexed,
    _iter_datasets,
    _param,
    _series,
    _try_dataset,
)

NAV_STATE = {
    0: "MANUAL",
    1: "ALTCTL",
    2: "POSCTL",
    3: "AUTO_MISSION",
    4: "AUTO_LOITER",
    5: "AUTO_RTL",
    6: "ACRO",
    7: "OFFBOARD",
    8: "STABILIZED",
    9: "AUTO_TAKEOFF",
    10: "AUTO_LAND",
    14: "AUTO_FOLLOW_TARGET",
    17: "AUTO_PRECLAND",
    20: "ORBIT",
}

# PX4 vehicle_gps_position.fix_type: 3=3D, 4=RTCM, 5=RTK float, 6=RTK fixed
GPS_3D_FIX = 3
CPU_LOAD_WARN = 0.80
CPU_LOAD_CRIT = 0.92
RAM_WARN = 0.85
PWM_HIGH = 1990.0
PWM_LOW = 1010.0
SAT_WARN = 8
EPH_WARN_M = 5.0
TEMP_WARN_C = 75.0
RC_RSSI_WARN = 20.0


def _coalesce(*arrays: Optional[np.ndarray]) -> Optional[np.ndarray]:
    for arr in arrays:
        if arr is not None:
            return arr
    return None


def _t0(ulog: ULog) -> float:
    return float(ulog.start_timestamp)


def _rel_s(ulog: ULog, ts: np.ndarray) -> np.ndarray:
    return (np.asarray(ts, dtype=float) - _t0(ulog)) / 1e6


def _metric(
    name: str,
    topic: str,
    unit: Optional[str],
    series: Optional[np.ndarray],
) -> Optional[MetricStats]:
    if series is None:
        return None
    finite = _finite(series)
    if finite.size == 0:
        return None
    return MetricStats(
        name=name,
        topic=topic,
        unit=unit,
        samples=int(finite.size),
        min=round(float(np.min(finite)), 4),
        max=round(float(np.max(finite)), 4),
        mean=round(float(np.mean(finite)), 4),
        std=round(float(np.std(finite)), 4),
        p95=round(float(np.percentile(finite, 95)), 4),
    )


def profile_topics(ulog: ULog) -> list[TopicProfile]:
    profiles: list[TopicProfile] = []
    for ds in ulog.data_list:
        ts = _series(ds.data, "timestamp")
        sample_n = int(ts.size) if ts is not None else 0
        if sample_n == 0 and ds.data:
            first = next(iter(ds.data.values()))
            sample_n = int(np.asarray(first).size)
        rate = None
        duration = None
        if ts is not None and ts.size >= 2:
            t = np.asarray(ts, dtype=float)
            duration = float((t[-1] - t[0]) / 1e6)
            if duration > 0:
                rate = round((ts.size - 1) / duration, 2)
        fields = sorted(str(k) for k in ds.data.keys() if k != "timestamp")
        profiles.append(
            TopicProfile(
                name=ds.name,
                instance=int(getattr(ds, "multi_id", 0) or 0),
                samples=sample_n,
                rate_hz=rate,
                duration_s=round(duration, 3) if duration is not None else None,
                fields=fields[:40],
            )
        )
    profiles.sort(key=lambda p: (p.name, p.instance))
    return profiles


def collect_metric_stats(ulog: ULog) -> list[MetricStats]:
    stats: list[MetricStats] = []
    specs: list[tuple[str, str, Optional[str], Optional[np.ndarray]]] = []

    batt = _try_dataset(ulog, "battery_status")
    if batt is not None:
        specs.extend(
            [
                ("pack_voltage", "battery_status", "V", _series(batt.data, "voltage_v", "voltage_filtered_v")),
                ("pack_current", "battery_status", "A", _series(batt.data, "current_a", "current_filtered_a")),
                ("remaining", "battery_status", "frac", _series(batt.data, "remaining")),
                ("discharged_mah", "battery_status", "mAh", _series(batt.data, "discharged_mah")),
            ]
        )

    gps = _try_dataset(ulog, "vehicle_gps_position")
    if gps is not None:
        specs.extend(
            [
                ("gps_fix_type", "vehicle_gps_position", None, _series(gps.data, "fix_type")),
                ("gps_satellites", "vehicle_gps_position", "count", _series(gps.data, "satellites_used")),
                ("gps_eph", "vehicle_gps_position", "m", _series(gps.data, "eph", "hdop")),
                ("gps_epv", "vehicle_gps_position", "m", _series(gps.data, "epv", "vdop")),
                ("gps_jamming", "vehicle_gps_position", None, _series(gps.data, "jamming_indicator", "jamming_state")),
            ]
        )

    local = _try_dataset(ulog, "vehicle_local_position")
    if local is not None:
        specs.extend(
            [
                ("local_x", "vehicle_local_position", "m", _series(local.data, "x")),
                ("local_y", "vehicle_local_position", "m", _series(local.data, "y")),
                ("local_z", "vehicle_local_position", "m", _series(local.data, "z")),
                ("local_vx", "vehicle_local_position", "m/s", _series(local.data, "vx")),
                ("local_vy", "vehicle_local_position", "m/s", _series(local.data, "vy")),
                ("local_vz", "vehicle_local_position", "m/s", _series(local.data, "vz")),
            ]
        )

    air = _try_dataset(ulog, "vehicle_air_data")
    if air is not None:
        specs.append(("baro_alt", "vehicle_air_data", "m", _series(air.data, "baro_alt_meter")))

    att = _try_dataset(ulog, "vehicle_attitude")
    if att is not None:
        for axis, field in enumerate(("rollspeed", "pitchspeed", "yawspeed")):
            specs.append((field, "vehicle_attitude", "rad/s", _series(att.data, field)))

    cpu = _try_dataset(ulog, "cpuload")
    if cpu is not None:
        specs.extend(
            [
                ("cpu_load", "cpuload", "frac", _series(cpu.data, "load")),
                ("ram_usage", "cpuload", "frac", _series(cpu.data, "ram_usage")),
            ]
        )

    rc = _try_dataset(ulog, "input_rc")
    if rc is not None:
        specs.extend(
            [
                ("rc_rssi", "input_rc", None, _series(rc.data, "rssi")),
                ("rc_lost", "input_rc", None, _series(rc.data, "rc_lost")),
            ]
        )

    radio = _try_dataset(ulog, "radio_status")
    if radio is not None:
        specs.extend(
            [
                ("telem_rssi", "radio_status", None, _series(radio.data, "rssi")),
                ("telem_rxerrors", "radio_status", "count", _series(radio.data, "rxerrors")),
            ]
        )

    dist = _try_dataset(ulog, "distance_sensor")
    if dist is not None:
        specs.append(("rangefinder_m", "distance_sensor", "m", _series(dist.data, "current_distance")))

    est = _try_dataset(ulog, "estimator_status")
    if est is not None:
        for field in (
            "mag_test_ratio",
            "vel_test_ratio",
            "pos_test_ratio",
            "hgt_test_ratio",
            "tas_test_ratio",
        ):
            specs.append((field, "estimator_status", "ratio", _series(est.data, field)))
        for axis in range(3):
            specs.append((f"vibe[{axis}]", "estimator_status", "m/s^2", _indexed(est.data, "vibe", axis)))

    imu = _try_dataset(ulog, "vehicle_imu")
    if imu is not None:
        specs.append(("imu_temp", "vehicle_imu", "C", _series(imu.data, "temperature")))
    accel = _try_dataset(ulog, "sensor_accel")
    if accel is not None:
        specs.append(("accel_temp", "sensor_accel", "C", _series(accel.data, "temperature")))

    mag = _try_dataset(ulog, "vehicle_magnetometer") or _try_dataset(ulog, "sensor_mag")
    if mag is not None:
        mx = _coalesce(_indexed(mag.data, "magnetometer_ga", 0), _series(mag.data, "x"))
        my = _coalesce(_indexed(mag.data, "magnetometer_ga", 1), _series(mag.data, "y"))
        mz = _coalesce(_indexed(mag.data, "magnetometer_ga", 2), _series(mag.data, "z"))
        if mx is not None and my is not None and mz is not None:
            n = min(mx.size, my.size, mz.size)
            mag_norm = np.hypot(np.hypot(mx[:n], my[:n]), mz[:n])
            specs.append(("mag_norm", mag.name, "gauss", mag_norm))

    airspeed = _try_dataset(ulog, "airspeed")
    if airspeed is not None:
        specs.append(("indicated_airspeed", "airspeed", "m/s", _series(airspeed.data, "indicated_airspeed_m_s")))

    wind = _try_dataset(ulog, "wind")
    if wind is not None:
        specs.extend(
            [
                ("wind_north", "wind", "m/s", _series(wind.data, "windspeed_north")),
                ("wind_east", "wind", "m/s", _series(wind.data, "windspeed_east")),
            ]
        )

    for name, topic, unit, series in specs:
        item = _metric(name, topic, unit, series)
        if item:
            stats.append(item)

    have = {(m.topic, m.name) for m in stats}
    stats.extend(_scan_remaining_metrics(ulog, have, cap=120))
    return stats


def _scan_remaining_metrics(
    ulog: ULog,
    have: set[tuple[str, str]],
    cap: int,
) -> list[MetricStats]:
    """커레이티드 목록에 없는 숫자 필드를 전 토픽에서 요약한다."""

    extra: list[MetricStats] = []
    for ds in ulog.data_list:
        for key, raw in ds.data.items():
            if key == "timestamp" or str(key).startswith("timestamp"):
                continue
            arr = np.asarray(raw)
            if arr.dtype.kind in {"U", "S", "O"}:
                continue
            if arr.ndim >= 2:
                cols = min(int(arr.shape[-1]), 8)
                for i in range(cols):
                    name = f"{key}[{i}]"
                    if (ds.name, name) in have:
                        continue
                    column = arr[..., i].reshape(-1)
                    item = _metric(name, ds.name, None, column)
                    if item is None:
                        continue
                    extra.append(item)
                    have.add((ds.name, name))
                    if len(extra) >= cap:
                        return extra
                continue
            if (ds.name, str(key)) in have:
                continue
            item = _metric(str(key), ds.name, None, arr)
            if item is None:
                continue
            extra.append(item)
            have.add((ds.name, str(key)))
            if len(extra) >= cap:
                return extra
    return extra


def kinematics(ulog: ULog) -> FlightKinematics:
    kin = FlightKinematics()
    status = _try_dataset(ulog, "vehicle_status")
    if status is not None:
        ts = _series(status.data, "timestamp")
        arm = _series(status.data, "arming_state")
        if ts is not None and arm is not None:
            t = _rel_s(ulog, ts)
            armed = np.asarray(arm, dtype=float) >= 2
            if t.size and armed.size:
                n = min(t.size, armed.size)
                if n >= 2 and np.any(armed[:n]):
                    dt = np.diff(t[:n])
                    kin.armed_s = round(float(np.sum(dt[armed[: n - 1]])), 2)

    local = _try_dataset(ulog, "vehicle_local_position")
    if local is None:
        return kin
    x = _series(local.data, "x")
    y = _series(local.data, "y")
    z = _series(local.data, "z")
    vx = _series(local.data, "vx")
    vy = _series(local.data, "vy")
    vz = _series(local.data, "vz")
    if x is not None and y is not None:
        xf, yf = _finite(x), _finite(y)
        n = min(xf.size, yf.size)
        if n >= 2:
            dx = np.diff(xf[:n])
            dy = np.diff(yf[:n])
            kin.distance_m = round(float(np.sum(np.hypot(dx, dy))), 2)
    if vx is not None and vy is not None:
        vxf = _finite(vx)
        vyf = _finite(vy)
        n = min(vxf.size, vyf.size)
        if n:
            kin.max_speed_mps = round(float(np.max(np.hypot(vxf[:n], vyf[:n]))), 3)
    if vz is not None:
        vzf = _finite(vz)
        if vzf.size:
            kin.max_abs_vz_mps = round(float(np.max(np.abs(vzf))), 3)
    if z is not None:
        zf = _finite(z)
        if zf.size:
            # NED: z down, altitude ≈ -z
            alt = -zf
            kin.alt_min_m = round(float(np.min(alt)), 2)
            kin.alt_max_m = round(float(np.max(alt)), 2)
            kin.alt_range_m = round(float(np.max(alt) - np.min(alt)), 2)
    return kin


def detect_gps(ulog: ULog, notes: list[str]) -> list[AnomalyFinding]:
    findings: list[AnomalyFinding] = []
    ds = _try_dataset(ulog, "vehicle_gps_position")
    if ds is None:
        notes.append("vehicle_gps_position 토픽이 없어 GNSS 품질을 평가하지 못했습니다.")
        return findings

    fix = _series(ds.data, "fix_type")
    sats = _series(ds.data, "satellites_used")
    eph = _series(ds.data, "eph", "hdop")
    jam = _series(ds.data, "jamming_state", "jamming_indicator")

    if fix is not None:
        finite = _finite(fix)
        if finite.size:
            peak = float(np.max(finite))
            no3d = float(np.mean(finite < GPS_3D_FIX))
            if peak < GPS_3D_FIX:
                findings.append(
                    AnomalyFinding(
                        code="gps_no_3d_fix",
                        title="GNSS 3D 픽스 없음",
                        severity=Severity.CRITICAL,
                        detector_source="px4_firmware_gate",
                        topic="vehicle_gps_position",
                        metric="fix_type",
                        measured_value=peak,
                        threshold=float(GPS_3D_FIX),
                        sample_ratio=round(no3d, 4),
                        detail=f"fix_type 최대 {peak:.0f} < 3 (3D). 전 구간의 {no3d:.0%}가 3D 미만입니다.",
                    )
                )
            elif no3d > 0.05:
                findings.append(
                    AnomalyFinding(
                        code="gps_fix_drop",
                        title="GNSS 3D 픽스 손실 구간",
                        severity=Severity.WARNING,
                        detector_source="px4_firmware_gate",
                        topic="vehicle_gps_position",
                        metric="fix_type",
                        measured_value=peak,
                        threshold=float(GPS_3D_FIX),
                        sample_ratio=round(no3d, 4),
                        detail=f"샘플의 {no3d:.1%}에서 fix_type < 3. 차폐·안테나·멀티패스를 점검하십시오.",
                    )
                )

    if sats is not None:
        finite = _finite(sats)
        if finite.size:
            smin = float(np.min(finite))
            if smin < SAT_WARN:
                findings.append(
                    AnomalyFinding(
                        code="gps_low_satellites",
                        title="GNSS 위성 수 부족",
                        severity=Severity.WARNING if smin >= 6 else Severity.CRITICAL,
                        detector_source="px4_firmware_gate",
                        topic="vehicle_gps_position",
                        metric="satellites_used",
                        measured_value=smin,
                        threshold=float(SAT_WARN),
                        unit="count",
                        detail=f"satellites_used 최저 {smin:.0f} (권장 관측 하한 {SAT_WARN}).",
                    )
                )

    if eph is not None:
        finite = _finite(eph)
        if finite.size:
            emax = float(np.max(finite))
            if emax >= EPH_WARN_M:
                findings.append(
                    AnomalyFinding(
                        code="gps_high_eph",
                        title="GNSS 수평 오차 큼",
                        severity=Severity.WARNING,
                        detector_source="px4_firmware_gate",
                        topic="vehicle_gps_position",
                        metric="eph",
                        measured_value=round(emax, 3),
                        threshold=EPH_WARN_M,
                        unit="m",
                        detail=f"eph/hdop 피크 {emax:.2f} m ≥ {EPH_WARN_M} m.",
                    )
                )

    if jam is not None:
        finite = _finite(jam)
        if finite.size and float(np.max(finite)) >= 1:
            findings.append(
                AnomalyFinding(
                    code="gps_jamming",
                    title="GNSS 재밍 지시값 활성",
                    severity=Severity.CRITICAL,
                    detector_source="px4_firmware_gate",
                    topic="vehicle_gps_position",
                    metric="jamming",
                    measured_value=float(np.max(finite)),
                    threshold=1.0,
                    detail=f"jamming_state/indicator 최대 {float(np.max(finite)):.0f}.",
                )
            )
    return findings


def detect_rc_link(ulog: ULog, notes: list[str]) -> list[AnomalyFinding]:
    findings: list[AnomalyFinding] = []
    status = _try_dataset(ulog, "vehicle_status")
    if status is not None:
        for field, title in (
            ("rc_signal_lost", "RC 신호 손실"),
            ("data_link_lost", "GCS 데이터링크 손실"),
            ("engine_failure", "엔진/모터 실패 플래그"),
            ("mission_failure", "미션 실패 플래그"),
            ("geofence_violated", "지오펜스 위반"),
        ):
            series = _series(status.data, field)
            if series is None:
                continue
            finite = _finite(series)
            if finite.size and int(np.max(finite)) >= 1:
                findings.append(
                    AnomalyFinding(
                        code=f"status_{field}",
                        title=title,
                        severity=Severity.CRITICAL,
                        detector_source="px4_firmware_gate",
                        topic="vehicle_status",
                        metric=field,
                        measured_value=float(int(np.max(finite))),
                        threshold=1.0,
                        detail=f"vehicle_status.{field}가 1 이상으로 올라갔습니다.",
                    )
                )

    rc = _try_dataset(ulog, "input_rc")
    if rc is None:
        notes.append("input_rc 토픽이 없어 RSSI를 평가하지 못했습니다.")
        return findings
    lost = _series(rc.data, "rc_lost")
    rssi = _series(rc.data, "rssi")
    if lost is not None:
        finite = _finite(lost)
        if finite.size and float(np.max(finite)) >= 1:
            findings.append(
                AnomalyFinding(
                    code="rc_lost",
                    title="input_rc.rc_lost 활성",
                    severity=Severity.CRITICAL,
                    detector_source="px4_firmware_gate",
                    topic="input_rc",
                    metric="rc_lost",
                    measured_value=float(np.max(finite)),
                    threshold=1.0,
                    detail="수신기 프레임 손실(rc_lost)이 기록되었습니다.",
                )
            )
    if rssi is not None:
        finite = _finite(rssi)
        if finite.size:
            rmin = float(np.min(finite))
            # 일부 스택은 rssi 0~100, 일부는 255 스케일
            scale_warn = RC_RSSI_WARN if rmin <= 100 else 50.0
            if 0 <= rmin < scale_warn:
                findings.append(
                    AnomalyFinding(
                        code="rc_low_rssi",
                        title="RC RSSI 낮음",
                        severity=Severity.WARNING,
                        detector_source="px4_firmware_gate",
                        topic="input_rc",
                        metric="rssi",
                        measured_value=round(rmin, 2),
                        threshold=scale_warn,
                        detail=f"RSSI 최저 {rmin:.1f}. 안테나·페이드·간섭을 점검하십시오.",
                    )
                )
    return findings


def detect_cpu(ulog: ULog, notes: list[str]) -> list[AnomalyFinding]:
    findings: list[AnomalyFinding] = []
    ds = _try_dataset(ulog, "cpuload")
    if ds is None:
        notes.append("cpuload 토픽이 없어 CPU/RAM을 평가하지 못했습니다.")
        return findings
    load = _series(ds.data, "load")
    ram = _series(ds.data, "ram_usage")
    if load is not None:
        finite = _finite(load)
        if finite.size:
            peak = float(np.max(finite))
            if peak >= CPU_LOAD_CRIT:
                sev, code_s = Severity.CRITICAL, CPU_LOAD_CRIT
            elif peak >= CPU_LOAD_WARN:
                sev, code_s = Severity.WARNING, CPU_LOAD_WARN
            else:
                sev, code_s = Severity.OK, CPU_LOAD_WARN
            if sev != Severity.OK:
                findings.append(
                    AnomalyFinding(
                        code="cpu_load_high",
                        title="FC CPU 부하 높음",
                        severity=sev,
                        detector_source="px4_firmware_gate",
                        topic="cpuload",
                        metric="load",
                        measured_value=round(peak, 3),
                        threshold=code_s,
                        unit="frac",
                        detail=f"cpuload.load 피크 {peak:.1%}.",
                    )
                )
    if ram is not None:
        finite = _finite(ram)
        if finite.size:
            peak = float(np.max(finite))
            if peak >= RAM_WARN:
                findings.append(
                    AnomalyFinding(
                        code="ram_usage_high",
                        title="FC RAM 사용량 높음",
                        severity=Severity.WARNING,
                        detector_source="px4_firmware_gate",
                        topic="cpuload",
                        metric="ram_usage",
                        measured_value=round(peak, 3),
                        threshold=RAM_WARN,
                        unit="frac",
                        detail=f"cpuload.ram_usage 피크 {peak:.1%}.",
                    )
                )
    return findings


def detect_actuator_sat(ulog: ULog, notes: list[str]) -> list[AnomalyFinding]:
    findings: list[AnomalyFinding] = []
    ds = _try_dataset(ulog, "actuator_outputs")
    if ds is None:
        notes.append("actuator_outputs 토픽이 없어 PWM 포화를 평가하지 못했습니다.")
        return findings
    sat_ratio_peak = 0.0
    sat_ch: list[str] = []
    for ch in range(16):
        series = _indexed(ds.data, "output", ch)
        if series is None:
            continue
        finite = _finite(series)
        if finite.size == 0:
            continue
        # 디스암 PWM(~900)은 제외하고 비행 중 대역만
        flying = finite[(finite >= 980) & (finite <= 2200)]
        if flying.size == 0:
            continue
        sat = float(np.mean((flying >= PWM_HIGH) | (flying <= PWM_LOW)))
        if sat >= 0.02:
            sat_ratio_peak = max(sat_ratio_peak, sat)
            sat_ch.append(f"output[{ch}]={sat:.1%}")
    if sat_ch:
        findings.append(
            AnomalyFinding(
                code="actuator_saturation",
                title="액추에이터 PWM 포화",
                severity=Severity.WARNING if sat_ratio_peak < 0.15 else Severity.CRITICAL,
                detector_source="px4_firmware_gate",
                topic="actuator_outputs",
                metric="output_sat_ratio",
                measured_value=round(sat_ratio_peak, 4),
                threshold=0.02,
                sample_ratio=round(sat_ratio_peak, 4),
                detail="PWM이 1010/1990 근처에 머문 채널: " + ", ".join(sat_ch[:8]),
            )
        )
    return findings


def detect_estimator_flags(ulog: ULog) -> list[AnomalyFinding]:
    findings: list[AnomalyFinding] = []
    ds = _try_dataset(ulog, "estimator_status")
    if ds is None:
        return findings
    for field, title, thr in (
        ("filter_fault_flags", "EKF 필터 폴트 플래그", 1.0),
        ("gps_check_fail_flags", "EKF GPS 검사 실패 플래그", 1.0),
        ("innovation_fault_flags", "EKF 혁신 폴트 플래그", 1.0),
    ):
        series = _series(ds.data, field)
        if series is None:
            continue
        finite = _finite(series)
        if finite.size and float(np.max(finite)) >= thr:
            findings.append(
                AnomalyFinding(
                    code=f"ekf_{field}",
                    title=title,
                    severity=Severity.CRITICAL if "fault" in field else Severity.WARNING,
                    detector_source="px4_firmware_gate",
                    topic="estimator_status",
                    metric=field,
                    measured_value=float(int(np.max(finite))),
                    threshold=thr,
                    detail=f"estimator_status.{field} 최대 {int(np.max(finite))}.",
                )
            )
    return findings


def detect_temperature(ulog: ULog) -> list[AnomalyFinding]:
    findings: list[AnomalyFinding] = []
    for topic in ("vehicle_imu", "sensor_accel", "sensor_gyro", "sensor_baro"):
        ds = _try_dataset(ulog, topic)
        if ds is None:
            continue
        temp = _series(ds.data, "temperature")
        if temp is None:
            continue
        finite = _finite(temp)
        if finite.size == 0:
            continue
        tmax = float(np.max(finite))
        if tmax >= TEMP_WARN_C:
            findings.append(
                AnomalyFinding(
                    code="imu_temperature_high",
                    title=f"{topic} 온도 높음",
                    severity=Severity.WARNING if tmax < 85 else Severity.CRITICAL,
                    detector_source="px4_firmware_gate",
                    topic=topic,
                    metric="temperature",
                    measured_value=round(tmax, 2),
                    threshold=TEMP_WARN_C,
                    unit="C",
                    detail=f"{topic}.temperature 피크 {tmax:.1f}°C.",
                )
            )
        break
    return findings


def detect_battery_energy(ulog: ULog, notes: list[str]) -> list[AnomalyFinding]:
    """잔량·경고 플래그는 로그 자체 BAT_* 임계값과 대조한다."""

    findings: list[AnomalyFinding] = []
    ds = _try_dataset(ulog, "battery_status")
    if ds is None:
        notes.append("battery_status 토픽이 없어 잔량 게이트를 평가하지 못했습니다.")
        return findings

    remaining = _series(ds.data, "remaining")
    warning_reason = _series(ds.data, "warning_reason")
    failsafe = _series(ds.data, "failsafe")
    low_thr = _param(ulog, "BAT_LOW_THR")
    crit_thr = _param(ulog, "BAT_CRIT_THR")
    emer_thr = _param(ulog, "BAT_EMERGEN_THR")

    if remaining is not None:
        finite = _finite(remaining)
        if finite.size:
            rmin = float(np.min(finite))
            gate = emer_thr or crit_thr or low_thr
            if emer_thr is not None and rmin <= emer_thr:
                findings.append(
                    AnomalyFinding(
                        code="battery_emergency",
                        title="배터리 비상 잔량",
                        severity=Severity.CRITICAL,
                        detector_source="log_self_params",
                        topic="battery_status",
                        metric="remaining",
                        measured_value=round(rmin, 4),
                        threshold=emer_thr,
                        unit="frac",
                        detail=f"remaining 최저 {rmin:.1%} ≤ BAT_EMERGEN_THR {emer_thr:.2f}.",
                    )
                )
            elif crit_thr is not None and rmin <= crit_thr:
                findings.append(
                    AnomalyFinding(
                        code="battery_critical",
                        title="배터리 치명 잔량",
                        severity=Severity.CRITICAL,
                        detector_source="log_self_params",
                        topic="battery_status",
                        metric="remaining",
                        measured_value=round(rmin, 4),
                        threshold=crit_thr,
                        unit="frac",
                        detail=f"remaining 최저 {rmin:.1%} ≤ BAT_CRIT_THR {crit_thr:.2f}.",
                    )
                )
            elif low_thr is not None and rmin <= low_thr:
                findings.append(
                    AnomalyFinding(
                        code="battery_low",
                        title="배터리 저전압 잔량",
                        severity=Severity.WARNING,
                        detector_source="log_self_params",
                        topic="battery_status",
                        metric="remaining",
                        measured_value=round(rmin, 4),
                        threshold=low_thr,
                        unit="frac",
                        detail=f"remaining 최저 {rmin:.1%} ≤ BAT_LOW_THR {low_thr:.2f}.",
                    )
                )
            elif gate is None and rmin <= 0.20:
                findings.append(
                    AnomalyFinding(
                        code="battery_low_observed",
                        title="배터리 잔량 20% 이하",
                        severity=Severity.WARNING,
                        detector_source="px4_firmware_gate",
                        topic="battery_status",
                        metric="remaining",
                        measured_value=round(rmin, 4),
                        threshold=0.20,
                        unit="frac",
                        detail=f"remaining 최저 {rmin:.1%}. 로그에 BAT_*_THR가 없어 관측 하한만 표시합니다.",
                    )
                )

    if warning_reason is not None:
        finite = _finite(warning_reason)
        if finite.size and float(np.max(finite)) >= 1:
            findings.append(
                AnomalyFinding(
                    code="battery_warning_reason",
                    title="배터리 warning_reason 활성",
                    severity=Severity.WARNING,
                    detector_source="px4_firmware_gate",
                    topic="battery_status",
                    metric="warning_reason",
                    measured_value=float(int(np.max(finite))),
                    threshold=1.0,
                    detail=f"battery_status.warning_reason 최대 {int(np.max(finite))}.",
                )
            )
    if failsafe is not None:
        finite = _finite(failsafe)
        if finite.size and float(np.max(finite)) >= 1:
            findings.append(
                AnomalyFinding(
                    code="battery_failsafe",
                    title="배터리 페일세이프 플래그",
                    severity=Severity.CRITICAL,
                    detector_source="px4_firmware_gate",
                    topic="battery_status",
                    metric="failsafe",
                    measured_value=float(int(np.max(finite))),
                    threshold=1.0,
                    detail="battery_status.failsafe가 활성화되었습니다.",
                )
            )
    return findings


def detect_dropouts(ulog: ULog) -> list[AnomalyFinding]:
    findings: list[AnomalyFinding] = []
    drops = list(getattr(ulog, "dropouts", None) or [])
    if not drops:
        return findings
    total_s = 0.0
    for item in drops:
        dur = getattr(item, "duration", None)
        if dur is None and isinstance(item, (tuple, list)) and len(item) >= 2:
            dur = item[1]
        try:
            total_s += float(dur) / (1e6 if float(dur) > 1e3 else 1.0)
        except (TypeError, ValueError):
            continue
    findings.append(
        AnomalyFinding(
            code="ulog_dropout",
            title="ULog 드롭아웃(기록 공백)",
            severity=Severity.WARNING if len(drops) < 8 else Severity.CRITICAL,
            detector_source="px4_firmware_gate",
            topic="ulog",
            metric="dropout_count",
            measured_value=float(len(drops)),
            threshold=1.0,
            detail=f"드롭아웃 {len(drops)}회, 대략 {total_s:.2f}s 공백. SD카드/CPU 부하를 점검하십시오.",
        )
    )
    return findings


def detect_logging_gaps(ulog: ULog) -> list[AnomalyFinding]:
    """주요 고속 토픽의 타임스탬프 점프를 찾는다."""

    findings: list[AnomalyFinding] = []
    for name in ("vehicle_attitude", "sensor_combined", "vehicle_local_position"):
        ds = _try_dataset(ulog, name)
        if ds is None:
            continue
        ts = _series(ds.data, "timestamp")
        if ts is None or ts.size < 16:
            continue
        t = np.asarray(ts, dtype=float)
        dt = np.diff(t)
        med = float(np.median(dt[dt > 0])) if np.any(dt > 0) else 0.0
        if med <= 0:
            continue
        jumps = dt > (20.0 * med)
        if np.any(jumps):
            worst = float(np.max(dt) / 1e6)
            findings.append(
                AnomalyFinding(
                    code="logging_gap",
                    title=f"{name} 샘플 간격 점프",
                    severity=Severity.WARNING,
                    detector_source="px4_firmware_gate",
                    topic=name,
                    metric="timestamp_gap_s",
                    measured_value=round(worst, 3),
                    threshold=round(20.0 * med / 1e6, 4),
                    unit="s",
                    sample_ratio=round(float(np.mean(jumps)), 4),
                    detail=f"중앙 dt {med/1e3:.2f}ms 대비 최대 공백 {worst:.3f}s.",
                )
            )
        break
    return findings


def build_timeline(ulog: ULog, _extra_logs: list[str]) -> list[TimelineEvent]:
    events: list[TimelineEvent] = []
    t0 = _t0(ulog)

    status = _try_dataset(ulog, "vehicle_status")
    if status is not None:
        ts = _series(status.data, "timestamp")
        nav = _series(status.data, "nav_state")
        arm = _series(status.data, "arming_state")
        fail = _series(status.data, "failsafe")
        if ts is not None and nav is not None:
            t = _rel_s(ulog, ts)
            n = min(t.size, nav.size)
            prev = None
            for i in range(n):
                cur = int(nav[i])
                if prev is None or cur != prev:
                    events.append(
                        TimelineEvent(
                            t_s=round(float(t[i]), 2),
                            kind="mode",
                            text=f"모드 {NAV_STATE.get(cur, str(cur))}",
                            severity=Severity.INFO,
                        )
                    )
                    prev = cur
        if ts is not None and arm is not None:
            t = _rel_s(ulog, ts)
            n = min(t.size, arm.size)
            prev = None
            for i in range(n):
                cur = int(arm[i])
                if prev is None or cur != prev:
                    events.append(
                        TimelineEvent(
                            t_s=round(float(t[i]), 2),
                            kind="arming",
                            text="시동" if cur >= 2 else "디스암",
                            severity=Severity.INFO if cur < 2 else Severity.WARNING,
                        )
                    )
                    prev = cur
        if ts is not None and fail is not None:
            t = _rel_s(ulog, ts)
            n = min(t.size, fail.size)
            prev = 0
            for i in range(n):
                cur = int(fail[i])
                if cur >= 1 and prev < 1:
                    events.append(
                        TimelineEvent(
                            t_s=round(float(t[i]), 2),
                            kind="failsafe",
                            text="Failsafe 진입",
                            severity=Severity.CRITICAL,
                        )
                    )
                prev = cur

    for msg in ulog.logged_messages or []:
        text = (getattr(msg, "message", None) or "").strip()
        ts = getattr(msg, "timestamp", None)
        if not text or ts is None:
            continue
        events.append(
            TimelineEvent(
                t_s=round((float(ts) - t0) / 1e6, 2),
                kind="log",
                text=text[:240],
                severity=Severity.WARNING,
            )
        )

    for item in list(getattr(ulog, "dropouts", None) or [])[:20]:
        ts = getattr(item, "timestamp", None)
        if ts is None and isinstance(item, (tuple, list)) and item:
            ts = item[0]
        if ts is None:
            continue
        events.append(
            TimelineEvent(
                t_s=round((float(ts) - t0) / 1e6, 2),
                kind="dropout",
                text="ULog dropout",
                severity=Severity.WARNING,
            )
        )

    events.sort(key=lambda e: (e.t_s, e.kind))
    # 로그 메시지가 너무 많으면 앞 80 + 페일세이프/모드 유지
    if len(events) > 120:
        important = [e for e in events if e.kind != "log"]
        logs = [e for e in events if e.kind == "log"][:40]
        events = sorted(important + logs, key=lambda e: e.t_s)
    return events


def extra_charts(ulog: ULog, max_points: int = 400) -> list[ChartSeries]:
    charts: list[ChartSeries] = []
    t0 = _t0(ulog)

    def add_line(ds_name: str, field: str, chart_id: str, title: str, ylab: str) -> None:
        ds = _try_dataset(ulog, ds_name)
        if ds is None:
            return
        ts = _series(ds.data, "timestamp")
        y = _coalesce(_series(ds.data, field), _indexed(ds.data, field, 0))
        if ts is None or y is None:
            return
        x, yy = _downsample_xy((np.asarray(ts, dtype=float) - t0) / 1e6, y, max_points)
        if x:
            charts.append(
                ChartSeries(
                    id=chart_id,
                    title=title,
                    x_label="시간 (s)",
                    y_label=ylab,
                    kind="line",
                    x=x,
                    y=yy,
                )
            )

    local = _try_dataset(ulog, "vehicle_local_position")
    if local is not None:
        ts = _series(local.data, "timestamp")
        z = _series(local.data, "z")
        if ts is not None and z is not None:
            x, y = _downsample_xy((np.asarray(ts, dtype=float) - t0) / 1e6, -np.asarray(z, dtype=float), max_points)
            if x:
                charts.append(
                    ChartSeries(
                        id="altitude_agl",
                        title="상대 고도 (-local.z)",
                        x_label="시간 (s)",
                        y_label="m",
                        kind="line",
                        x=x,
                        y=y,
                    )
                )

    add_line("battery_status", "current_a", "battery_current", "배터리 전류", "A")
    add_line("battery_status", "remaining", "battery_remaining", "배터리 잔량", "frac")
    add_line("cpuload", "load", "cpu_load", "CPU 부하", "frac")
    add_line("cpuload", "ram_usage", "ram_usage", "RAM 사용량", "frac")
    add_line("input_rc", "rssi", "rc_rssi", "RC RSSI", "")
    add_line("estimator_status", "mag_test_ratio", "ekf_mag_ratio", "EKF mag test_ratio", "ratio")
    add_line("estimator_status", "vel_test_ratio", "ekf_vel_ratio", "EKF vel test_ratio", "ratio")
    add_line("estimator_status", "pos_test_ratio", "ekf_pos_ratio", "EKF pos test_ratio", "ratio")
    gps = _try_dataset(ulog, "vehicle_gps_position")
    if gps is not None:
        ts = _series(gps.data, "timestamp")
        sats = _series(gps.data, "satellites_used")
        if ts is not None and sats is not None:
            x, y = _downsample_xy((np.asarray(ts, dtype=float) - t0) / 1e6, sats, max_points)
            if x:
                charts.append(
                    ChartSeries(
                        id="gps_sats",
                        title="GNSS 위성 수",
                        x_label="시간 (s)",
                        y_label="count",
                        kind="line",
                        x=x,
                        y=y,
                    )
                )

    act = _try_dataset(ulog, "actuator_outputs")
    if act is not None:
        ts = _series(act.data, "timestamp")
        o0 = _indexed(act.data, "output", 0)
        if ts is not None and o0 is not None:
            x, y = _downsample_xy((np.asarray(ts, dtype=float) - t0) / 1e6, o0, max_points)
            if x:
                charts.append(
                    ChartSeries(
                        id="pwm_ch0",
                        title="액추에이터 PWM ch0",
                        x_label="시간 (s)",
                        y_label="us",
                        kind="line",
                        x=x,
                        y=y,
                    )
                )
    return charts


def build_executive_summary(
    *,
    overall: Severity,
    findings: list[AnomalyFinding],
    kin: FlightKinematics,
    topics: list[TopicProfile],
    duration_s: float,
) -> list[str]:
    lines: list[str] = []
    lines.append(
        f"종합 심각도 {overall.value}. 로그 길이 {duration_s:.1f}s, 기록 토픽 {len(topics)}개."
    )
    if kin.armed_s is not None:
        lines.append(f"시동 유지 약 {kin.armed_s:.1f}s.")
    if kin.distance_m is not None:
        lines.append(f"수평 이동 거리 약 {kin.distance_m:.1f} m.")
    if kin.max_speed_mps is not None:
        lines.append(f"수평 속도 피크 {kin.max_speed_mps:.2f} m/s.")
    if kin.alt_range_m is not None:
        lines.append(
            f"상대고도 범위 {kin.alt_min_m:.1f} ~ {kin.alt_max_m:.1f} m (Δ {kin.alt_range_m:.1f} m)."
        )

    crit = [f for f in findings if f.severity == Severity.CRITICAL]
    warn = [f for f in findings if f.severity == Severity.WARNING]
    if crit:
        lines.append("치명: " + "; ".join(f.title for f in crit[:6]))
    if warn:
        lines.append("경고: " + "; ".join(f.title for f in warn[:8]))
    if not crit and not warn:
        lines.append("펌웨어 게이트 기준 치명/경고 이상은 없습니다. Canonical 불일치는 별도 처방 절을 보십시오.")
    lines.append(
        "수치 처방은 02_Canonical SSOT만 사용합니다. Canonical에 없는 IMU/EKF 게이트 튜닝값은 발명하지 않았습니다."
    )
    return lines
