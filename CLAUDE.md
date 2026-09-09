# Apex HiveStrike Platform (주식회사 에이펙스하이브스트라이크)

## 프로젝트 개요
드론 개발자 및 엔지니어를 위한 올인원 개발 플랫폼:
1. PX4/ArduPilot ULog(.ulg) 및 바이너리 로그 분석 백엔드 API
2. 드론 엔지니어링 2nd-Brain 지식 베이스
3. 시계열 센서 차트 및 비행 궤적 웹 대시보드

## 기술 스택
- Backend: Python 3.11+, FastAPI, Uvicorn, pyulog, Pydantic v2
- Frontend: Next.js (App Router), TypeScript, Tailwind CSS, Plotly.js
- Architecture: Monorepo
  - services/api: FastAPI 기반 로그 분석 백엔드
  - apps/web: Next.js 대시보드 웹 애플리케이션
  - knowledge/: 지식 파이프라인 (01_Evidence, 02_Canonical, 03_Discovery)

## 개발 규칙
- Python: 타입 힌트(Type Hints) 필수, Pydantic v2 스키마 분리, 비동기(async) 핸들러 기본 사용
- 에러 처리: 비행 로그 파싱 실패 시 명확한 HTTP 상태 코드 및 한글 에러 메시지 반환
- 커밋 규칙: feat:, fix:, docs:, refactor: 접두사 사용
