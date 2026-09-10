# Drone Engineering Platform - Context & Roadmap

## 0. OpenClaw Core 허브 (단일 진입점)
- [x] OpenClaw Gateway 24h 상주 (`127.0.0.1:18789`, LaunchAgent)
- [x] 네이티브 텔레그램 채널 (OpenClaw `channels.telegram`) — `telegram_bridge.py` 폴링 폐기
- [x] `hive-second-brain` Skill: Canonical 검색 / Evidence capture / Discovery 적재 / 승격 / ULog 분석 / lint / watch / digest
- [x] 서브에이전트 라우팅: `drone-rnd` (Qwen 3.6) · `researcher` (Gemma 4) · `hermes` (Nous 도구) · Claude Code
- 계약 파일: `config/openclaw-hub.yaml`
- 설치: `python3 scripts/install_openclaw_hub.py`

## 1. Current Progress (구축 완료 항목)
- [x] FastAPI 백엔드 지식 수집/승격 API (`/knowledge/ingest`, `/knowledge/promote`)
- [x] OpenClaw `drone-rnd` (Qwen 3.6 27B) 기반 무비용 웹 타깃 심층 크롤링 및 03_Discovery 자동 적재
- [x] Claude Code CLI (`claude -p`) 연동 무비용 로컬 볼트 RAG 기술 질의응답
- [x] 텔레그램은 OpenClaw 게이트웨이가 최초 수신. 승격은 채팅에서 `승격 <category> <doc_id>`
- [x] Obsidian 계층 구조 (Evidence -> Discovery -> Canonical) 그래프 뷰 시각화
- [x] ULog(`.ulg`) 종합 진단 엔진 (전 토픽 스캔 · 예상 문제/대응 정비 · 한글 PDF)
- [x] Vault 계약 (`knowledge/SCHEMA.md`): Evidence SHA-256, Discovery `decision`, Canonical 2+ 위키링크, Index/log 트랜잭션
- [x] OpenClaw cron: `hive-source-watch` (8h) · `hive-daily-digest` (매일 08:00 KST)
- [x] 웹 대시보드 `apps/web` (볼트 현황 + ULog 차트 + 대응 정비)

## 2. Upcoming Priorities (고도화 개발 목록)
- [ ] **비행 로그 .tlog 파서 (Priority 1 잔여)**:
  - ArduPilot `.tlog` 업로드 파서
- [ ] **수집 채널 전방위 확장 (Priority 2)**:
  - ArduPilot 공식 포럼, PX4 GitHub Issues/PR, 디스코드 웹훅 연동
- [ ] **지능형 자동 링킹**:
  - 수집 문서 내 EKF2/MAVLink 등 핵심 키워드 감지 시 `[[Canonical]]` 자동 위키링크 생성

## 3. Key Directories
- `config/`: 수집 타깃(`targets.yaml`) 및 OpenClaw 허브 계약(`openclaw-hub.yaml`)
- `knowledge/`: 옵시디언 지식 볼트 (`01_Evidence`, `02_Canonical`, `03_Discovery`)
- `skills/hive-second-brain/`: OpenClaw Skill + `scripts/hive_vault.py`
- `openclaw/hermes-workspace/`: Hermes 서브에이전트 워크스페이스
- `services/api/`: FastAPI 백엔드 (엔진/승격 API, UI가 아님)
- `services/agent/telegram_bridge.py`: **legacy fallback only** (`HIVE_LEGACY_TELEGRAM_BRIDGE=1`)
- `services/collector/source_watch.py`: GitHub Releases API + Discourse JSON 워치
- `services/collector/cron_collector.py`: **deprecated** (`HIVE_LEGACY_CRON_COLLECTOR=1`)
