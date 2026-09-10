---
name: hive-second-brain
slug: hive-second-brain
version: 1.0.0
description: "Apex HiveStrike 옵시디언 볼트 도구. Canonical 검색, Discovery 적재, 인간 승인 승격, ULog(.ulg) 이상 진단. 드론 지식·로그 분석·파라미터 처방 요청에 사용."
metadata:
  openclaw:
    requires:
      bins: ["python3"]
    os: ["darwin", "linux"]
---

# hive-second-brain

Apex HiveStrike 세컨드 브레인을 OpenClaw 공식 Skill로 노출한다.
볼트 루트: `{baseDir}/../../knowledge` (저장소 `Apex HiveStrike-2nd-brain-template`).

CLI: `python3 {baseDir}/scripts/hive_vault.py`

## 언제 쓰는가

- PX4/ArduPilot/ROS2 파라미터·페일세이프·EKF2 질문
- Canonical SSOT 조회 또는 Discovery 가설 적재
- 텔레그램/CLI로 `.ulg` 비행 로그 이상 진단
- 사용자가 **명시적으로** Canonical 승격을 요청한 경우

단순 잡담에는 쓰지 않는다.

## 신뢰도 규칙 (위반 금지)

| 계층 | 경로 | 에이전트 의무 |
|---|---|---|
| Evidence | `knowledge/01_Evidence` | 미검증 원천. 수치의 근거로 쓰지 않음 |
| Discovery | `knowledge/03_Discovery` | 가설만 기록. `status: needs_review` |
| Canonical | `knowledge/02_Canonical` | **유일한 SSOT**. 파라미터 처방은 여기 숫자만 |

- Canonical에 없는 튜닝값을 발명하지 않는다.
- `02_Canonical`에 직접 파일을 만들거나 `reviewed: true`로 쓰지 않는다.
- 승격은 사용자 명시 승인 후에만 `promote` 서브커맨드를 실행한다.

## 도구 맵

```bash
# Canonical(+옵션 Discovery) 검색
python3 {baseDir}/scripts/hive_vault.py search "EKF2_HGT_REF" --layer canonical

# 가설 적재 (항상 03_Discovery)
python3 {baseDir}/scripts/hive_vault.py ingest \
  --title "실내 고도 소스 가설" \
  --category 01_Flight_Controllers \
  --content "..."

# Evidence 원문 고정 (SHA-256, 동일 해시면 중복 스킵)
python3 {baseDir}/scripts/hive_vault.py capture \
  --title "PX4 release notes" --source "https://..." \
  --category 01_Flight_Controllers --body "..."

# 인간 승인 승격 (Index/log 트랜잭션)
python3 {baseDir}/scripts/hive_vault.py promote \
  --doc-id DISC-xxx --category 01_Flight_Controllers

# ULog 종합 진단(전 토픽 스캔) → 03_Discovery/06_Troubleshooting (+ PDF)
python3 {baseDir}/scripts/hive_vault.py analyze /path/to/flight.ulg --pdf

# Canonical에서 추출된 PX4 파라미터 목록
python3 {baseDir}/scripts/hive_vault.py canonical-params

# 계약 검사 / 소스 워치 / 일일 다이제스트
python3 {baseDir}/scripts/hive_vault.py lint
python3 {baseDir}/scripts/hive_vault.py watch
python3 {baseDir}/scripts/hive_vault.py digest
```

텔레그램 첨부 `.ulg`는 게이트웨이가 저장한 로컬 경로를 `analyze`에 넘긴다.
`.tlog`/`.bin`은 아직 미지원이라고 짧게 거절한다.

## 라우팅 (OpenClaw 허브)

이 스킬을 쓰는 에이전트는 **직접 답하기 전에** 역할이 맞는지 확인한다.

- 드론 기술 Q&A·로그 진단·Canonical 조회 → `drone-rnd` (이미 본인이면 이 스킬 실행)
- 웹/논문 사실 조사만 → `researcher` (읽기: `search` / 쓰기는 Discovery만)
- 브라우저 클릭·computer_use·깊은 로컬 GUI 조작 → `sessions_spawn` `agentId=hermes`
- 심층 코드/아키텍처 추론 → `developer` 또는 Claude Code (`claude -p`), Canonical 수치는 이 스킬로 먼저 읽는다

`main`(Olympus HQ)은 전문 업무를 가로채지 않고 위 에이전트로 위임한다.

## 응답 형식

1. Canonical에서 찾은 값과 출처 `[[위키링크]]`를 먼저 제시
2. Discovery/Evidence는 "미검증"이라고 표시
3. 로그 분석은 심각도, 이상 코드, Canonical 처방만 요약 (장문 Discovery 경로는 마지막 한 줄)
