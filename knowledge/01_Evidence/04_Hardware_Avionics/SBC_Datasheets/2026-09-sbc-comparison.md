---
id: EVI-HW-SBC-001
title: 드론 자율비행용 SBC 보드 특성 및 스펙 비교 분석
source_type: web_research
relevance: high
target_systems: [ROS2, PX4, ArduPilot]
status: raw
created_at: 2026-09-10
tags: [sbc, hardware, jetson, raspberry_pi, odroid, beaglebone]
---

# 드론 자율비행용 SBC 보드 특성 비교

## 1. 하드웨어 스펙 비교표

| 보드 모델 | CPU 아키텍처 | GPU / NPU | RAM | 권장 용도 및 한계 |
| :--- | :--- | :--- | :--- | :--- |
| **Jetson Orin Nano** | ARM Cortex-A78AE (6코어) | 1024-core Ampere (40 TOPS) | 4GB / 8GB | 실시간 VIO, 딥러닝 객체인식 표준 (고가) |
| **Raspberry Pi 5** | ARM Cortex-A76 2.4GHz (4코어) | VideoCore VII (NPU 별매) | 4GB / 8GB | ROS2 기본 제어, 경량 오도메트리 |
| **Odroid XU4** | Cortex-A15 + A7 (빅리틀 8코어) | Mali-T628 MP6 | 2GB LPDDR3 | 32비트 레거시, 최신 ROS2 패키지 빌드 병목 |
| **BeagleBone Blue** | Cortex-A8 1.0GHz (싱글코어) | 없음 | 512MB DDR3 | 로우레벨 제어 교육용 (SLAM/비전 연산 불가) |

## 2. 수집 메모 및 트러블슈팅 포인트
- **GNSS-Denied 환경**: VIO(Visual-Inertial Odometry) 알고리즘 구동 시 최소 Raspberry Pi 4/5 또는 Jetson 시리즈 필수.
- **통신 병목**: PX4와 통신 시 단순 MAVROS보다는 Micro-XRCE-DDS 프로토콜 권장.
