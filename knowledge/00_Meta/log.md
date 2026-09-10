---
id: META-LOG-001
title: Apex HiveStrike Vault Operation Log
status: verified
reviewed: true
tags: [log, append-only]
---

# Vault Operation Log

앞 항목을 지우거나 고쳐 쓰지 않는다. 새 항목만 위에 추가한다.

## [2026-09-10] upgrade | OpenClaw watch/digest

- `services/knowledge/vault.py` SHA-256 Evidence, Discovery decision, promote Index/log
- `services/collector/source_watch.py` GitHub Releases API + Discourse JSON
- OpenClaw cron: `hive-source-watch` (8h), `hive-daily-digest` (08:00 KST)
- ULog 리포트 경로: `03_Discovery/06_Troubleshooting`
- `cron_collector.py` deprecated

## [2026-09-10] bootstrap | SCHEMA

- 영향: [[SCHEMA]] [[Index]]
- 내용: ains-lab 계약을 HiveStrike 도메인 칸 위에 도입. Evidence 불변+SHA-256, Discovery decision, Canonical 승격 시 Index/log 트랜잭션.
