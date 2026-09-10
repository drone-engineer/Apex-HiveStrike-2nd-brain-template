# AGENT BEHAVIOR SPECIFICATION (2nd-Brain Framework)

이 문서는 Apex HiveStrike 지식 베이스 및 백엔드 코드를 다루는 모든 AI 에이전트(Claude Code, Cursor, LangGraph 등)의 의무 행동 지침서입니다.

---

## 1. 지식 라이프사이클 및 신뢰도 규칙 (Knowledge Lifecycle)

1. **01_Evidence (Raw Ingestion)**:
   - 외부 논문, 웹 문서, 비행 로그 원본을 적재하는 공간입니다.
   - 에이전트는 이 폴더의 내용을 '아직 검증되지 않은 외부 주장'으로 취급해야 합니다.
2. **03_Discovery (Hypothesis & Triage)**:
   - 엔지니어링 가설, 분석 메모, 실험 계획이 작성되는 공간입니다.
   - `status: draft` 또는 `needs_review`를 가지며, 최종 판단의 근거로 사용하지 않습니다.
3. **02_Canonical (Single Source of Truth - SSOT)**:
   - 반드시 인간 검증(`reviewed: true`, `status: verified`)을 거쳐 승격된 공식 표준 문서입니다.
   - **에이전트는 코드 작성, 파라미터 튜닝, 트러블슈팅 답변 시 오직 이 폴더의 수치와 지침만을 진실로 채택합니다.**

---

## 2. 문서 작성 시 필수 준수 사항 (Frontmatter & Wiki-Links)

에이전트가 새로운 지식 문서를 생성할 때는 반드시 다음 3가지를 지켜야 합니다:

1. **YAML Frontmatter 필수 필드**:
   - `id`: 고유 식별자 (예: `CAN-HW-001`, `DISC-AUTO-002`)
   - `title`: 명확한 문서 제목
   - `status`: `raw` | `draft` | `needs_review` | `verified`
   - `reviewed`: boolean (`true` / `false`)
   - `tags`: 도메인 태그 배열
2. **양방향 위키링크(Obsidian Graph Linking)**:
   - 고립된(Orphan) 문서를 만들지 않습니다.
   - 활성 Canonical은 `[[문서파일명]]`을 자기 제외 **2개 이상** 연결합니다 (보통 `[[Index]]` + `[[SCHEMA]]`).
   - Discovery는 `decision: pending|accepted|contested|deferred|rejected`를 넣습니다.
3. **인간 승인 절차 (Human-in-the-Loop)**:
   - 에이전트는 임의로 `02_Canonical` 폴더에 문서를 생성하거나 `status: verified`로 설정할 수 없습니다.
   - 에이전트의 산출물은 기본적으로 `03_Discovery`에 `status: needs_review`로 생성되어야 합니다.

---

## 3. OpenClaw 허브 의무

- 사용자 메시지의 단일 진입점은 OpenClaw Gateway다. 별도 텔레그램 브리지를 띄우지 않는다.
- 볼트 읽기/쓰기/ULog 분석은 `hive-second-brain` Skill (`skills/hive-second-brain/scripts/hive_vault.py`)만 사용한다.
- 디렉터리·메타데이터·무결성의 권위는 `knowledge/SCHEMA.md`다. AGENTS.md와 어긋나면 SCHEMA를 따른다.
- 브라우저 클릭·computer_use·깊은 로컬 GUI 작업은 `hermes` 서브에이전트로 위임한다.
- 드론 기술 질의·로그 진단은 `drone-rnd`에 위임하고, 조사만 필요하면 `researcher`에 위임한다.
- 소스 워치/다이제스트는 OpenClaw cron (`hive-source-watch`, `hive-daily-digest`)이 `hive_vault.py watch|digest`를 실행한다. `cron_collector.py`는 사용하지 않는다.
