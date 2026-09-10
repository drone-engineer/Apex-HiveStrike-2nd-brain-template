---
id: DISC-HW-SBC-001
title: 자율비행 체급별 SBC 선정 가설 및 실시간성 검증 계획
created_at: 2026-09-10
author: 이수용
status: draft
reviewed: false
tags: [sbc, companion_computer, jetson, rpi, vio]
---

# 자율비행 체급별 SBC 선정 가설

- 상위 인덱스: [[Index]]
- 기반 원본 증거: [[2026-09-sbc-comparison]]
- 승격 예정 표준: [[sbc_selection_matrix]]

## 1. 플랫폼 티어별 채택 가설
- **티어 1 (경량/저비용 GPS 항법)**: Raspberry Pi 4/5
  - 역할: MAVLink/ROS2 브릿지, 기본 웨이포인트 경로 생성
  - 한계: 고해상도 VIO 실시간 처리 불가
- **티어 2 (GNSS-Denied 실내 자율비행/SLAM)**: Jetson Orin Nano (8GB)
  - 역할: VINS-Fusion / ORB-SLAM3 온보드 실시간 연산 (CUDA 가속 활용)
  - 필수 조건: 독립 5V/5A 이상 전원 공급(BEC) 및 방열 대책

## 2. 검증 항목 (Canonical 승격 조건)
- [ ] SITL 환경에서 가상 센서 데이터 처리 지연시간(Latency) 20ms 이내 확인
- [ ] 실기체 호버링 상태에서 VIO 연산 중 CPU 사용률 75% 미만 유지 여부
