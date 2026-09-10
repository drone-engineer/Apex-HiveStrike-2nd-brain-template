---
id: CAN-HW-SBC-001
title: 드론 자율비행 컴패니언 보드 표준 선정 매트릭스
created_at: 2026-09-10
verified_at: 2026-09-10
author: 이수용
status: verified
reviewed: true
verified_by: 이수용
tags: [sbc, hardware, verified, jetson, rpi]
---

# 컴패니언 보드 표준 선정 매트릭스 (공식 표준)

- 상위 인덱스: [[Index]]
- 검증 완료된 가설: [[sbc_selection_hypothesis]]
- 원본 증거 레퍼런스: [[2026-09-sbc-comparison]]

## 1. 하드웨어 티어 표준

| 비행 모드 | 권장 SBC | 최소 전원 규격 | 비행 제어기 통신 프로토콜 |
| :--- | :--- | :--- | :--- |
| **기본 Waypoint 항법** | Raspberry Pi 4/5 (4GB) | 5V / 3A BEC | MAVLink (UART/USB) |
| **실내 VIO / SLAM 자율비행** | Jetson Orin Nano (8GB) | 5V / 5A 독립 전원 | Micro-XRCE-DDS (High-baud UART) |

## 2. 주의사항 및 하드웨어 가이드라인
- **VIO 프레임워크 호환성**: RPi 계열은 ORB-SLAM3/VINS-Fusion 풀스택 실시간 가속 불가. 실내 자율비행 기체는 Jetson 계열을 의무 표준으로 지정.
- **전원 분리**: 모터 급기동 시 전압 강하로 인한 SBC 리셋을 방지하기 위해 FC 전원선과 SBC 전원선은 완전히 분리된 독립 BEC를 사용할 것.
