---
id: META-SCHEMA-001
title: Apex HiveStrike Vault Contract
status: verified
reviewed: true
tags: [schema, contract, 2nd-brain]
---

# Apex HiveStrike Vault Contract

이 파일이 디렉터리·메타데이터·무결성의 **권위 있는 계약**이다. [AGENTS.md](../AGENTS.md)와 어긋나면 이 문서를 따른다.

## 계층

| 계층 | 경로 | 역할 |
|---|---|---|
| Inbox | `knowledge/00_Inbox` | 미분류. Evidence도 Canonical도 아님 |
| Evidence | `knowledge/01_Evidence/<domain>` | 불변 원천. 본문 수정 금지. SHA-256 필수 |
| Discovery | `knowledge/03_Discovery/<domain>` | 가설. `status: needs_review`, `decision` 필수 |
| Canonical | `knowledge/02_Canonical/<domain>` | 인간 검증 SSOT만 |
| Archive | `knowledge/_archive` | 폐기된 Canonical |

도메인 칸 (05 없음):

- `01_Flight_Controllers`
- `02_Autonomy_ROS`
- `03_Communications`
- `04_Hardware_Avionics`
- `06_Flight_Logs` — Evidence만 (로그 원본 포인터)
- `06_Troubleshooting` — Discovery만 (ULog 리포트)
- `06_Runbooks` — Canonical만 (승격된 절차)

## Frontmatter

공통: `id`, `title`, `status`, `reviewed`, `tags`

- Evidence: `status: raw`, `reviewed: false`, `source`, `sha256`, `ingested_at`
- Discovery: `status: needs_review`, `reviewed: false`, `decision: pending\|accepted\|contested\|deferred\|rejected`, `category`, `sources` (Evidence 상대경로)
- Canonical: `status: verified`, `reviewed: true`, `type: concept\|comparison\|query\|runbook`, `sources` (실존 Evidence 경로), `category`

## 규칙

1. Evidence 본문은 최초 기록 후 변경하지 않는다. 해석은 Discovery/Canonical에 쓴다.
2. Canonical `sources`는 존재하는 Evidence `.md` 만 허용한다. URL만으로는 부족하다.
3. 활성 Canonical은 `[[wikilink]]`를 자기 제외 2개 이상 가진다.
4. Canonical 생성·승격·폐기는 `00_Meta/Index.md`와 `00_Meta/log.md`를 같은 트랜잭션으로 갱신한다. log는 앞줄을 지우지 않는다.
5. 에이전트는 Canonical을 직접 만들지 않는다. `hive_vault.py promote`는 사용자 명시 승인 후에만.
6. 파라미터 처방 수치는 Canonical만 진실이다.

## Keep / Drop (크론)

Keep: 파라미터 델타, 고장 모드, 브레이킹 체인지, 링크/전원 스펙.
Drop: HTML 껍데기, 타임아웃 문구, 스타 수, 무기 목적 논의.
