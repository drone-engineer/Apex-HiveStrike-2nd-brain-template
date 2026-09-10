#!/usr/bin/env python3
"""OpenClaw 허브에 hive-second-brain 스킬과 hermes 에이전트를 등록한다.

openclaw.json 안의 시크릿은 출력하지 않는다.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILL_SRC = REPO / "skills" / "hive-second-brain"
HERMES_WS = REPO / "openclaw" / "hermes-workspace"
MULTI_SKILLS = Path("/Users/drone_engineer/cursor/multi_agent/skills")
OPENCLAW_JSON = Path.home() / ".openclaw" / "openclaw.json"
SKILL_NAME = "hive-second-brain"


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True)


def _link(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_symlink() or dest.exists():
        if dest.is_symlink() and dest.resolve() == SKILL_SRC.resolve():
            return dest
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
        elif dest.is_dir() and not dest.is_symlink():
            raise SystemExit(f"기존 디렉터리와 충돌: {dest}")
    dest.symlink_to(SKILL_SRC, target_is_directory=True)
    return dest


def symlink_skill() -> list[Path]:
    return [
        _link(MULTI_SKILLS / SKILL_NAME),
        _link(HERMES_WS / "skills" / SKILL_NAME),
    ]


def ensure_hermes_agent() -> None:
    listed = _run(["openclaw", "agents", "list"])
    text = f"{listed.stdout}\n{listed.stderr}"
    cleaned = re.sub(r"\x1b\[[0-9;]*m", "", text)
    if re.search(r"^[-*] hermes\b", cleaned, re.MULTILINE):
        print("hermes 에이전트: 이미 등록됨")
        return
    result = _run(
        [
            "openclaw",
            "agents",
            "add",
            "hermes",
            "--non-interactive",
            f"--workspace={HERMES_WS}",
            "--model=anthropic/claude-haiku-4-5",
        ]
    )
    err = f"{result.stdout}\n{result.stderr}"
    if result.returncode != 0 and "already exists" not in err:
        raise SystemExit(f"openclaw agents add hermes 실패:\n{err}")
    if "already exists" in err:
        print("hermes 에이전트: 이미 등록됨")
        return
    print("hermes 에이전트: 신규 등록")


def patch_openclaw_json() -> None:
    backup = OPENCLAW_JSON.with_name(
        f"openclaw.json.bak-hive-hub-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    )
    shutil.copy2(OPENCLAW_JSON, backup)
    data = json.loads(OPENCLAW_JSON.read_text(encoding="utf-8"))
    agents = data.get("agents", {}).get("list", [])

    def find(agent_id: str) -> dict | None:
        for item in agents:
            if item.get("id") == agent_id:
                return item
        return None

    main = find("main")
    if main:
        allow = main.setdefault("subagents", {}).setdefault("allowAgents", [])
        if "hermes" not in allow:
            allow.append("hermes")
        skills = main.setdefault("skills", [])
        if SKILL_NAME not in skills:
            skills.append(SKILL_NAME)

    for agent_id in ("drone-rnd", "researcher", "hermes"):
        agent = find(agent_id)
        if not agent:
            continue
        skills = agent.setdefault("skills", [])
        if SKILL_NAME not in skills:
            skills.append(SKILL_NAME)
        if agent_id == "hermes":
            agent["description"] = (
                "도구 실행: Hermes CLI (browser/computer_use/code_execution). 지식 SSOT는 hive-second-brain."
            )
            agent["workspace"] = str(HERMES_WS)
            agent.setdefault("identity", {}).update(
                {
                    "name": "Hermes Tool Runner",
                    "emoji": "🧰",
                    "theme": "브라우저·컴퓨터 사용·로컬 도구 실행 서브에이전트",
                }
            )
            tools = agent.setdefault("tools", {})
            tools["profile"] = "coding"
            allow = tools.setdefault("alsoAllow", [])
            for name in ("exec", "session_status"):
                if name not in allow:
                    allow.append(name)

    skills_root = data.setdefault("skills", {})
    load = skills_root.setdefault("load", {})
    extra_dirs = load.setdefault("extraDirs", [])
    allow_links = load.setdefault("allowSymlinkTargets", [])
    hive_skills = str(SKILL_SRC.parent)
    if hive_skills not in extra_dirs:
        extra_dirs.append(hive_skills)
    if hive_skills not in allow_links:
        allow_links.append(hive_skills)
    skills_root.setdefault("entries", {}).setdefault(SKILL_NAME, {"enabled": True})

    OPENCLAW_JSON.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"openclaw.json 패치 완료 (backup={backup.name})")


def register_cron_jobs() -> None:
    """declaration-key 로 멱등 등록. 시크릿은 출력하지 않는다."""

    venv_py = REPO / "services" / "api" / "venv" / "bin" / "python3"
    cli = SKILL_SRC / "scripts" / "hive_vault.py"
    watch_cmd = f"{venv_py} {cli} watch"
    digest_cmd = f"{venv_py} {cli} digest"
    jobs = [
        [
            "openclaw",
            "cron",
            "add",
            "--name",
            "hive-source-watch",
            "--display-name",
            "HiveStrike 소스 워치",
            "--every",
            "8h",
            "--declaration-key",
            "hive-source-watch",
            "--command",
            watch_cmd,
            "--command-cwd",
            str(REPO),
            "--timeout-seconds",
            "300",
            "--no-output-timeout-seconds",
            "300",
            "--no-deliver",
            "--description",
            "PX4/ROS/MAVLink/HW 소스 변화만 Evidence+Discovery에 적재",
        ],
        [
            "openclaw",
            "cron",
            "add",
            "--name",
            "hive-daily-digest",
            "--display-name",
            "HiveStrike Discovery 다이제스트",
            "--cron",
            "0 8 * * *",
            "--tz",
            "Asia/Seoul",
            "--declaration-key",
            "hive-daily-digest",
            "--command",
            digest_cmd,
            "--command-cwd",
            str(REPO),
            "--timeout-seconds",
            "120",
            "--announce",
            "--channel",
            "telegram",
            "--to",
            "278187608",
            "--description",
            "검토 대기 Discovery 일일 요약",
        ],
    ]
    for cmd in jobs:
        result = _run(cmd)
        err = f"{result.stdout}\n{result.stderr}".strip()
        key = cmd[cmd.index("--declaration-key") + 1]
        if result.returncode != 0:
            print(f"cron {key}: 실패 ({result.returncode})")
            continue
        print(f"cron {key}: 등록/갱신 완료")
        if err and "token" not in err.lower():
            print(err[:400])


def main() -> None:
    for dest in symlink_skill():
        print(f"스킬 심볼릭 링크: {dest} → {SKILL_SRC}")
    ensure_hermes_agent()
    patch_openclaw_json()
    register_cron_jobs()
    print("다음: 게이트웨이가 새 에이전트/스킬을 읽도록 LaunchAgent를 재시작합니다.")


if __name__ == "__main__":
    main()
