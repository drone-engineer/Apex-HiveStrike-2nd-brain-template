#!/usr/bin/env python3
"""OpenClaw hive-second-brain CLI — 볼트 검색/적재/승격/ULog 분석."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
REPO_ROOT = SKILL_DIR.parents[1]
VAULT = REPO_ROOT / "knowledge"
CANONICAL = VAULT / "02_Canonical"
DISCOVERY = VAULT / "03_Discovery"
EVIDENCE = VAULT / "01_Evidence"
API_VENV_ROOT = REPO_ROOT / "services" / "api" / "venv"
REPO_VENV_ROOT = REPO_ROOT / ".venv"

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


def _ensure_repo_on_path() -> None:
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def _layer_dir(layer: str) -> Path:
    mapping = {
        "canonical": CANONICAL,
        "discovery": DISCOVERY,
        "evidence": EVIDENCE,
    }
    if layer not in mapping:
        raise SystemExit(f"알 수 없는 layer: {layer}")
    return mapping[layer]


def cmd_search(query: str, layer: str, limit: int) -> None:
    layers = ["canonical", "discovery", "evidence"] if layer == "all" else [layer]
    needle = query.lower()
    hits: list[dict[str, str]] = []
    for name in layers:
        root = _layer_dir(name)
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.md")):
            text = path.read_text(encoding="utf-8", errors="replace")
            if needle not in text.lower() and needle not in path.name.lower():
                continue
            snippet = ""
            for line in text.splitlines():
                if needle in line.lower():
                    snippet = line.strip()[:240]
                    break
            if not snippet:
                snippet = path.stem
            hits.append(
                {
                    "layer": name,
                    "id": path.stem,
                    "path": str(path.relative_to(REPO_ROOT)),
                    "snippet": snippet,
                    "ssot": name == "canonical",
                }
            )
            if len(hits) >= limit:
                break
        if len(hits) >= limit:
            break
    print(json.dumps({"query": query, "hits": hits}, ensure_ascii=False, indent=2))


def cmd_read(doc_id: str, layer: str) -> None:
    root = _layer_dir(layer)
    matches = list(root.rglob(f"{doc_id}.md"))
    if not matches:
        raise SystemExit(f"문서를 찾을 수 없습니다: {layer}/{doc_id}")
    path = matches[0]
    print(path.read_text(encoding="utf-8"))


def cmd_ingest(title: str, content: str, category: str, doc_id: str | None) -> None:
    _ensure_repo_on_path()
    from services.knowledge.vault import write_discovery

    result = write_discovery(
        title=title,
        content=content,
        category=category,
        sources=[],
        doc_id=doc_id,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_capture(title: str, source: str, body: str, category: str, doc_id: str | None) -> None:
    _ensure_repo_on_path()
    from services.knowledge.vault import capture_evidence

    result = capture_evidence(
        category=category,
        source=source,
        body=body,
        title=title,
        doc_id=doc_id,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_promote(doc_id: str, category: str) -> None:
    _ensure_repo_on_path()
    from services.knowledge.vault import promote_discovery

    try:
        result = promote_discovery(doc_id, category)
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_lint() -> None:
    _ensure_repo_on_path()
    from services.knowledge.vault import lint_vault

    issues = lint_vault()
    print(json.dumps([issue.__dict__ for issue in issues], ensure_ascii=False, indent=2))
    if issues:
        raise SystemExit(1)


def cmd_digest() -> None:
    _ensure_repo_on_path()
    from services.knowledge.vault import digest_discovery

    result = digest_discovery()
    print(result["text"])
    print(json.dumps({"count": result["count"], "path": result["path"]}, ensure_ascii=False))


def cmd_watch() -> None:
    _reexec_venv_if_needed(extra=("yaml",))
    _ensure_repo_on_path()
    from services.collector.source_watch import run_watch

    print(json.dumps(run_watch(), ensure_ascii=False, indent=2))


def cmd_reindex() -> None:
    _ensure_repo_on_path()
    from services.knowledge.vault import rebuild_index

    rebuild_index()
    print(json.dumps({"status": "reindexed"}, ensure_ascii=False))


def cmd_analyze(ulog_path: str, save_report: bool, pdf_out: str | None = None) -> None:
    path = Path(ulog_path).expanduser()
    if not path.is_file():
        raise SystemExit(f"로그 파일이 없습니다: {path}")

    _reexec_venv_if_needed(extra=("numpy", "pydantic", "pyulog", "fpdf"))
    _ensure_repo_on_path()
    from services.analyzer.ulog_analyzer import ULogAnalyzer

    report = ULogAnalyzer(repo_root=REPO_ROOT).analyze(
        path, original_filename=path.name, save_report=save_report
    )
    if pdf_out is not None:
        from services.analyzer.pdf_report import write_analysis_pdf

        dest = Path(pdf_out).expanduser() if pdf_out else path.with_suffix(".pdf")
        write_analysis_pdf(report, dest)
        report.pdf_path = str(dest)
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))


def _reexec_venv_if_needed(extra: tuple[str, ...] = ("numpy", "pydantic", "pyulog")) -> None:
    """필요한 모듈이 없으면 API venv로 재실행한다."""

    missing = False
    for name in extra:
        try:
            __import__(name)
        except ImportError:
            missing = True
            break
    if not missing:
        return
    for root in (API_VENV_ROOT, REPO_VENV_ROOT):
        py = root / "bin" / "python3"
        if not py.is_file():
            continue
        if Path(sys.prefix).resolve() == root.resolve():
            continue
        os.execv(str(py), [str(py), str(Path(__file__).resolve()), *sys.argv[1:]])
    raise SystemExit(f"{'/'.join(extra)} 가 없습니다. services/api/venv 를 구성하십시오.")


def cmd_canonical_params() -> None:
    _reexec_venv_if_needed(extra=("numpy", "pydantic", "pyulog"))
    _ensure_repo_on_path()
    from services.analyzer.ulog_analyzer import load_canonical_catalog

    catalog = load_canonical_catalog(CANONICAL)
    payload = {
        "params": {
            name: {
                "value": p.value,
                "source_id": p.source_id,
                "source_file": p.source_file,
                "unit": p.unit,
            }
            for name, p in catalog.params.items()
        },
        "hardware": [
            {"topic": h.topic, "text": h.text, "source_file": h.source_file}
            for h in catalog.hardware
        ],
        "docs": catalog.source_docs,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Apex HiveStrike 세컨드 브레인 CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_search = sub.add_parser("search")
    p_search.add_argument("query")
    p_search.add_argument(
        "--layer",
        choices=["canonical", "discovery", "evidence", "all"],
        default="canonical",
    )
    p_search.add_argument("--limit", type=int, default=12)

    p_read = sub.add_parser("read")
    p_read.add_argument("doc_id")
    p_read.add_argument(
        "--layer",
        choices=["canonical", "discovery", "evidence"],
        default="canonical",
    )

    p_ing = sub.add_parser("ingest")
    p_ing.add_argument("--title", required=True)
    p_ing.add_argument("--content", required=True)
    p_ing.add_argument("--category", default="01_Flight_Controllers")
    p_ing.add_argument("--doc-id")

    p_cap = sub.add_parser("capture")
    p_cap.add_argument("--title", required=True)
    p_cap.add_argument("--source", required=True)
    p_cap.add_argument("--body", required=True)
    p_cap.add_argument("--category", default="01_Flight_Controllers")
    p_cap.add_argument("--doc-id")

    p_pro = sub.add_parser("promote")
    p_pro.add_argument("--doc-id", required=True)
    p_pro.add_argument("--category", required=True)

    p_an = sub.add_parser("analyze")
    p_an.add_argument("ulog")
    p_an.add_argument("--no-save", action="store_true")
    p_an.add_argument(
        "--pdf",
        nargs="?",
        const="",
        default=None,
        help="PDF 저장 경로. 값 없이 --pdf 만 주면 로그와 같은 이름의 .pdf",
    )

    sub.add_parser("canonical-params")
    sub.add_parser("lint")
    sub.add_parser("digest")
    sub.add_parser("watch")
    sub.add_parser("reindex")

    args = parser.parse_args()
    if args.cmd == "search":
        cmd_search(args.query, args.layer, args.limit)
    elif args.cmd == "read":
        cmd_read(args.doc_id, args.layer)
    elif args.cmd == "ingest":
        cmd_ingest(args.title, args.content, args.category, args.doc_id)
    elif args.cmd == "capture":
        cmd_capture(args.title, args.source, args.body, args.category, args.doc_id)
    elif args.cmd == "promote":
        cmd_promote(args.doc_id, args.category)
    elif args.cmd == "analyze":
        cmd_analyze(args.ulog, save_report=not args.no_save, pdf_out=args.pdf)
    elif args.cmd == "canonical-params":
        cmd_canonical_params()
    elif args.cmd == "lint":
        cmd_lint()
    elif args.cmd == "digest":
        cmd_digest()
    elif args.cmd == "watch":
        cmd_watch()
    elif args.cmd == "reindex":
        cmd_reindex()


if __name__ == "__main__":
    main()
