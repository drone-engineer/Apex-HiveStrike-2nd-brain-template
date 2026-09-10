# Apex HiveStrike 2nd-Brain

주식회사 에이펙스하이브스트라이크의 드론 엔지니어링 지식 볼트 + 비행 로그 진단 플랫폼입니다.

- Obsidian 볼트: `knowledge/` (`01_Evidence` → `03_Discovery` → `02_Canonical`)
- 계약: `knowledge/SCHEMA.md`, `AGENTS.md`
- OpenClaw Skill: `skills/hive-second-brain/`
- ULog 분석: `services/analyzer/ulog_analyzer.py`

## 빠른 실행

```bash
python3 -m venv services/api/venv
source services/api/venv/bin/activate
pip install -r services/api/requirements.txt

# 볼트 CLI
python3 skills/hive-second-brain/scripts/hive_vault.py search "EKF2_HGT_REF" --layer canonical
python3 skills/hive-second-brain/scripts/hive_vault.py lint
python3 skills/hive-second-brain/scripts/hive_vault.py watch
python3 skills/hive-second-brain/scripts/hive_vault.py digest
```

ULog 분석:

```bash
python3 skills/hive-second-brain/scripts/hive_vault.py analyze /path/to/flight.ulg
```

OpenClaw 허브 설치(로컬 게이트웨이):

```bash
python3 scripts/install_openclaw_hub.py
```

텔레그램 폴링 브리지(`telegram_bridge.py`)는 쓰지 않습니다. 진입점은 OpenClaw Gateway입니다.

## 신뢰도

파라미터·튜닝 수치는 `knowledge/02_Canonical` (`reviewed: true`)만 SSOT입니다. 에이전트 산출물은 `03_Discovery`에 `needs_review`로만 적재됩니다.
