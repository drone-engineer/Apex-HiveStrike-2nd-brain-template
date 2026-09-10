#!/bin/bash
# deprecated: OpenClaw cron 잡 hive-source-watch 가 hive_vault.py watch 를 실행한다.
if [ "${HIVE_LEGACY_CRON_COLLECTOR}" != "1" ]; then
  echo "run_cron_collector.sh 는 deprecated 입니다."
  echo "OpenClaw cron: hive-source-watch → hive_vault.py watch"
  echo "강제 실행: HIVE_LEGACY_CRON_COLLECTOR=1"
  exit 1
fi

PROJECT_DIR="/Users/drone_engineer/cursor/Apex HiveStrike-2nd-brain-template"
cd "$PROJECT_DIR" || exit 1
"$PROJECT_DIR/services/api/venv/bin/python" "$PROJECT_DIR/services/collector/cron_collector.py" >> "$PROJECT_DIR/cron_collector.log" 2>&1
