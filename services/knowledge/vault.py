"""볼트 계약 구현: 불변 Evidence, Discovery 가설, Canonical 승격 트랜잭션."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
VAULT = REPO_ROOT / "knowledge"
EVIDENCE = VAULT / "01_Evidence"
DISCOVERY = VAULT / "03_Discovery"
CANONICAL = VAULT / "02_Canonical"
INDEX = VAULT / "00_Meta" / "Index.md"
LOG = VAULT / "00_Meta" / "log.md"

PROMOTE_DEST = {
    "06_Troubleshooting": "06_Runbooks",
}

SKIP_NAMES = {"README.md", "SCHEMA.md"}
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
_WIKI_RE = re.compile(r"\[\[([^\]|#]+)(?:[#|][^\]]*)?\]\]")
_GARBAGE = (
    "uh oh!",
    "there was an error while loading",
    "timed out after",
    "openclaw 분석 실패",
)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip("\"'")
    return meta, text[match.end() :]


def _fm_get(meta: dict[str, str], key: str) -> str:
    return meta.get(key, "")


def _unique_doc_id(folder: Path, prefix: str, stamp: str) -> tuple[str, Path]:
    doc_id = f"{prefix}-{stamp}"
    path = folder / f"{doc_id}.md"
    suffix = 1
    while path.exists():
        doc_id = f"{prefix}-{stamp}-{suffix:02d}"
        path = folder / f"{doc_id}.md"
        suffix += 1
    return doc_id, path


def find_evidence_hash(sha: str) -> Optional[Path]:
    if not EVIDENCE.is_dir():
        return None
    for path in EVIDENCE.rglob("*.md"):
        if path.name in SKIP_NAMES:
            continue
        meta, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        if _fm_get(meta, "sha256") == sha:
            return path
    return None


def capture_evidence(
    *,
    category: str,
    source: str,
    body: str,
    title: str,
    doc_id: Optional[str] = None,
) -> dict[str, object]:
    """원문을 Evidence에 고정한다. 동일 해시가 있으면 새로 쓰지 않는다."""

    digest = sha256_text(body.strip())
    existing = find_evidence_hash(digest)
    if existing:
        return {
            "status": "duplicate",
            "sha256": digest,
            "path": str(existing.relative_to(REPO_ROOT)),
            "doc_id": existing.stem,
        }

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = EVIDENCE / category
    folder.mkdir(parents=True, exist_ok=True)
    if doc_id:
        path = folder / f"{doc_id}.md"
    else:
        doc_id, path = _unique_doc_id(folder, "EVD", stamp)
    text = f"""---
id: {doc_id}
title: {title}
status: raw
reviewed: false
source: {source}
sha256: {digest}
ingested_at: {stamp}
category: {category}
tags: [evidence, immutable]
---

# {title}

- 상위 인덱스: [[Index]]
- 계약: [[SCHEMA]]

## Source
{source}

## Body
{body.strip()}
"""
    path.write_text(text, encoding="utf-8")
    return {
        "status": "captured",
        "sha256": digest,
        "path": str(path.relative_to(REPO_ROOT)),
        "doc_id": doc_id,
    }


def write_discovery(
    *,
    title: str,
    content: str,
    category: str,
    sources: list[str],
    doc_id: Optional[str] = None,
    decision: str = "pending",
    extra_links: Optional[list[str]] = None,
) -> dict[str, object]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = DISCOVERY / category
    folder.mkdir(parents=True, exist_ok=True)
    if doc_id:
        path = folder / f"{doc_id}.md"
    else:
        doc_id, path = _unique_doc_id(folder, "DISC", stamp)
    source_lines = "\n".join(f"- `{item}`" for item in sources) or "- (none)"
    links = extra_links or ["Index", "SCHEMA"]
    if len(links) < 2:
        links = list(dict.fromkeys(links + ["Index", "SCHEMA"]))
    wiki = " ".join(f"[[{name}]]" for name in links)
    text = f"""---
id: {doc_id}
title: {title}
status: needs_review
reviewed: false
decision: {decision}
category: {category}
type: concept
tags: [discovery, needs_review]
---

# {title}

- 상위: {wiki}
- 처리: hive-second-brain compile

## Sources
{source_lines}

## 본문
{content}
"""
    path.write_text(text, encoding="utf-8")
    return {
        "status": "ingested",
        "doc_id": doc_id,
        "path": str(path.relative_to(REPO_ROOT)),
        "reviewed": False,
        "decision": decision,
    }


def _canonical_entries() -> list[tuple[str, str, Path]]:
    rows: list[tuple[str, str, Path]] = []
    if not CANONICAL.is_dir():
        return rows
    for path in sorted(CANONICAL.rglob("*.md")):
        if path.name in SKIP_NAMES:
            continue
        meta, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        if _fm_get(meta, "reviewed") != "true":
            continue
        title = _fm_get(meta, "title") or path.stem
        category = path.parent.name
        rows.append((category, title, path))
    return rows


def rebuild_index() -> None:
    grouped: dict[str, list[str]] = {}
    for category, title, path in _canonical_entries():
        grouped.setdefault(category, []).append(f"- {title}: [[{path.stem}]]")

    sections = []
    for category in sorted(grouped):
        sections.append(f"### {category}\n" + "\n".join(grouped[category]))
    body = "\n\n".join(sections) or "- (활성 Canonical 없음)"

    pending: list[str] = []
    if DISCOVERY.is_dir():
        for path in sorted(DISCOVERY.rglob("*.md")):
            if path.name in SKIP_NAMES:
                continue
            meta, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
            if _fm_get(meta, "reviewed") == "true":
                continue
            title = _fm_get(meta, "title") or path.stem
            pending.append(f"- [{path.parent.name}] {title}: [[{path.stem}]]")
    pending_body = "\n".join(pending[:40]) or "- (검토 대기 없음)"

    INDEX.write_text(
        f"""---
id: META-INDEX-001
title: Apex HiveStrike Drone Knowledge Graph Index
status: verified
reviewed: true
tags: [index, moc, drone, 2nd-brain]
---

# Apex HiveStrike 지식 베이스 색인 (MOC)

계약: [[SCHEMA]] · 이력: [[log]]

## 도메인별 공식 표준 (Canonical SSOT)

{body}

## 검토 대기 (Discovery)

Discovery는 `needs_review`이며 최종 근거가 아니다. 승격은 인간만 한다.

{pending_body}
""",
        encoding="utf-8",
    )


def append_log(action: str, subject: str, paths: list[str]) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d")
    bullets = "\n".join(f"- `{item}`" for item in paths)
    block = f"\n## [{stamp}] {action} | {subject}\n\n{bullets}\n"
    current = LOG.read_text(encoding="utf-8") if LOG.is_file() else ""
    if current.startswith("---"):
        # insert after frontmatter+title
        marker = "# Vault Operation Log\n"
        if marker in current:
            head, tail = current.split(marker, 1)
            # keep first paragraph after title
            parts = tail.split("\n## ", 1)
            intro = parts[0]
            rest = ("\n## " + parts[1]) if len(parts) > 1 else ""
            LOG.write_text(head + marker + intro + block + rest, encoding="utf-8")
            return
    LOG.write_text(current + block, encoding="utf-8")


def promote_discovery(doc_id: str, category: str) -> dict[str, object]:
    disc = DISCOVERY / category / f"{doc_id}.md"
    if not disc.is_file():
        raise FileNotFoundError(f"Discovery 파일이 없습니다: {disc}")
    dest_cat = PROMOTE_DEST.get(category, category)
    dest_dir = CANONICAL / dest_cat
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{doc_id}.md"
    text = disc.read_text(encoding="utf-8")
    text = text.replace("status: needs_review", "status: verified")
    text = text.replace("status: draft", "status: verified")
    text = text.replace("reviewed: false", "reviewed: true")
    if "decision:" in text:
        text = re.sub(r"^decision:.*$", "decision: accepted", text, count=1, flags=re.M)
    dest.write_text(text, encoding="utf-8")
    disc.unlink()
    rebuild_index()
    append_log("promote", doc_id, [str(dest.relative_to(REPO_ROOT))])
    return {
        "status": "promoted",
        "doc_id": doc_id,
        "path": str(dest.relative_to(REPO_ROOT)),
        "reviewed": True,
    }


@dataclass
class LintIssue:
    path: str
    rule: str
    message: str


def lint_vault() -> list[LintIssue]:
    issues: list[LintIssue] = []

    for path in EVIDENCE.rglob("*.md"):
        if path.name in SKIP_NAMES:
            continue
        text = path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        rel = str(path.relative_to(REPO_ROOT))
        digest = _fm_get(meta, "sha256")
        if not digest:
            issues.append(LintIssue(rel, "evidence.sha256", "sha256 필드가 없습니다."))
            continue
        stored = text.split("## Body\n", 1)[-1].strip() if "## Body\n" in text else body.strip()
        if sha256_text(stored) != digest:
            issues.append(LintIssue(rel, "evidence.drift", "본문이 sha256과 다릅니다."))

    for path in CANONICAL.rglob("*.md"):
        if path.name in SKIP_NAMES:
            continue
        text = path.read_text(encoding="utf-8")
        meta, _ = parse_frontmatter(text)
        rel = str(path.relative_to(REPO_ROOT))
        if _fm_get(meta, "reviewed") != "true":
            issues.append(LintIssue(rel, "canonical.reviewed", "reviewed: true 가 아닙니다."))
        links = {item.strip() for item in _WIKI_RE.findall(text)}
        links.discard(path.stem)
        if len(links) < 2:
            issues.append(
                LintIssue(rel, "canonical.wikilinks", f"활성 위키링크 {len(links)}개 (최소 2).")
            )

    return issues


def digest_discovery() -> dict[str, object]:
    pending: list[dict[str, str]] = []
    for path in sorted(DISCOVERY.rglob("*.md")):
        if path.name in SKIP_NAMES:
            continue
        meta, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        if _fm_get(meta, "reviewed") == "true":
            continue
        pending.append(
            {
                "id": path.stem,
                "title": _fm_get(meta, "title") or path.stem,
                "category": path.parent.name,
                "decision": _fm_get(meta, "decision") or "pending",
            }
        )
    lines = ["HiveStrike 일일 Discovery 다이제스트", ""]
    if not pending:
        lines.append("검토 대기 문서 없음.")
    else:
        for item in pending[:40]:
            lines.append(
                f"- [{item['decision']}] `{item['category']}` {item['title']} "
                f"→ 승격 {item['category']} {item['id']}"
            )
    text = "\n".join(lines)
    out = VAULT / "00_Meta" / "digest-latest.md"
    out.write_text(
        f"""---
id: META-DIGEST-LATEST
title: Latest Discovery Digest
status: needs_review
reviewed: false
tags: [digest]
---

# Latest Discovery Digest

{text}
""",
        encoding="utf-8",
    )
    return {"count": len(pending), "path": str(out.relative_to(REPO_ROOT)), "text": text}


def looks_like_garbage(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in _GARBAGE)
