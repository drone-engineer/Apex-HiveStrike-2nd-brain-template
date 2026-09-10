"""피드/API로 01~04 소스를 보고, 변화가 있을 때만 Evidence+Discovery에 적재한다."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.knowledge.vault import (  # noqa: E402
    capture_evidence,
    looks_like_garbage,
    write_discovery,
)

CONFIG = REPO_ROOT / "config" / "targets.yaml"
UA = "ApexHiveStrikeVault/1.0"


def _fetch(url: str, timeout: int = 25) -> str:
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/json, text/plain"})
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return raw.decode("utf-8", errors="replace")


def _github_owner_repo(url: str) -> tuple[str, str]:
    parts = [p for p in url.rstrip("/").split("/") if p]
    if "releases" in parts:
        idx = parts.index("releases")
        return parts[idx - 2], parts[idx - 1]
    return parts[-2], parts[-1]


def _github_releases(url: str) -> str:
    if "api.github.com" not in url:
        owner, repo = _github_owner_repo(url)
        url = f"https://api.github.com/repos/{owner}/{repo}/releases?per_page=3"
    payload = json.loads(_fetch(url))
    lines: list[str] = []
    for rel in payload[:3]:
        lines.append(f"# {rel.get('tag_name')} — {rel.get('name')}")
        lines.append(f"published: {rel.get('published_at')}")
        body = (rel.get("body") or "")[:4000]
        lines.append(body)
        lines.append("")
    return "\n".join(lines).strip()


def _github_tags(url: str) -> str:
    if "api.github.com" not in url:
        owner, repo = _github_owner_repo(url)
        url = f"https://api.github.com/repos/{owner}/{repo}/tags?per_page=5"
    payload = json.loads(_fetch(url))
    lines: list[str] = []
    for tag in payload[:5]:
        commit = (tag.get("commit") or {}).get("sha", "")
        lines.append(f"- {tag.get('name')} sha={commit}")
    return "\n".join(lines).strip()


def _discourse_latest(url: str) -> str:
    json_url = url if url.endswith(".json") else url.rstrip("/") + ".json"
    payload = json.loads(_fetch(json_url))
    topics = payload.get("topic_list", {}).get("topics", [])
    lines: list[str] = []
    for topic in topics[:8]:
        lines.append(
            f"- {topic.get('title')} (id={topic.get('id')}, "
            f"bumped={topic.get('bumped_at') or topic.get('last_posted_at')})"
        )
    return "\n".join(lines).strip()


def fetch_source(kind: str, url: str) -> str:
    if kind == "github_releases":
        return _github_releases(url)
    if kind == "github_tags":
        return _github_tags(url)
    if kind == "discourse":
        return _discourse_latest(url)
    return _fetch(url)


def _compile_note(name: str, keep: list[str], raw: str) -> str:
    return (
        f"소스: {name}\n"
        f"keep 필드: {', '.join(keep)}\n\n"
        f"## 원천에서 관측된 최근 항목\n{raw}\n\n"
        "파라미터 수치가 Canonical에 없으면 발명하지 말고 decision=pending 으로 둔다.\n"
        "Canonical 대조: SSOT 없음 또는 기존 문서와 비교 필요."
    )


def run_watch() -> dict[str, Any]:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []
    for target in config.get("targets", []):
        if not target.get("enabled", False):
            continue
        tid = target["id"]
        try:
            raw = fetch_source(target.get("kind", "discourse"), target["url"])
        except (URLError, TimeoutError, json.JSONDecodeError, KeyError, ValueError) as exc:
            results.append({"id": tid, "status": "fetch_error", "error": str(exc)})
            continue
        if not raw:
            results.append({"id": tid, "status": "empty"})
            continue
        if looks_like_garbage(raw):
            results.append({"id": tid, "status": "skipped_garbage"})
            continue

        ev = capture_evidence(
            category=target["category"],
            source=target["url"],
            body=raw,
            title=f"[EVD] {target['name']}",
            doc_id=None,
        )
        if ev["status"] == "duplicate":
            results.append({"id": tid, "status": "unchanged", "sha256": ev["sha256"]})
            continue

        category = target.get("discovery_category", target["category"])
        domain_link = {
            "01_Flight_Controllers": "CAN-FC-PX4-FAILSAFE",
            "04_Hardware_Avionics": "sbc_selection_matrix",
        }.get(category)
        extra = ["Index", "SCHEMA"]
        if domain_link:
            extra.append(domain_link)
        note = _compile_note(target["name"], target.get("keep", []), raw[:2500])
        disc = write_discovery(
            title=f"[Watch] {target['name']}",
            content=note,
            category=category,
            sources=[str(ev["path"])],
            extra_links=extra,
        )
        results.append(
            {
                "id": tid,
                "status": "updated",
                "evidence": ev["path"],
                "discovery": disc["path"],
            }
        )
    return {"results": results}


if __name__ == "__main__":
    print(json.dumps(run_watch(), ensure_ascii=False, indent=2))
