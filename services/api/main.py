import sys
import os
import shutil
import asyncio
import tempfile
from pathlib import Path
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from typing import Optional

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))
from services.agent.graph import app as agent_app
from services.analyzer.schemas import AnalysisReport
from services.analyzer.ulog_analyzer import ULogAnalyzer, ULogParseError

api = FastAPI(
    title="Apex HiveStrike Drone Agent API",
    description="2nd-Brain 지식 파이프라인, 승격 백엔드, ULog 이상 진단 API",
    version="0.7.0"
)

api.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_MAX_ULOG_BYTES = 200 * 1024 * 1024

class IngestRequest(BaseModel):
    doc_id: str
    title: str
    raw_content: str
    category: str
    is_human_verified: bool = False

class PromoteRequest(BaseModel):
    doc_id: str
    category: str

@api.get("/")
def read_root():
    return {"status": "online", "service": "Apex HiveStrike Core", "version": "0.7.0"}


@api.get("/vault/overview")
def vault_overview():
    from services.knowledge.vault import vault_overview as build_overview

    return build_overview()


@api.post("/logs/analyze", response_model=AnalysisReport)
async def analyze_flight_log(
    file: UploadFile = File(..., description="PX4 ULog (.ulg) 파일"),
    save_report: bool = True,
) -> AnalysisReport:
    """업로드된 .ulg 전 토픽을 스캔해 종합 진단·통계·타임라인과 Canonical 처방을 반환한다."""

    filename = file.filename or "upload.ulg"
    suffix = Path(filename).suffix.lower() or ".ulg"
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=422, detail="업로드된 파일이 비어 있습니다.")
    if len(payload) > _MAX_ULOG_BYTES:
        raise HTTPException(
            status_code=413,
            detail="로그 파일이 200MB를 초과합니다. 더 짧은 구간 로그를 업로드하십시오.",
        )

    tmp_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(prefix="ulog_", suffix=suffix, delete=False) as tmp:
            tmp.write(payload)
            tmp_path = tmp.name
        analyzer = ULogAnalyzer()
        return await asyncio.to_thread(
            analyzer.analyze,
            tmp_path,
            filename,
            save_report,
        )
    except ULogParseError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


@api.post("/logs/report/pdf")
async def render_report_pdf(report: AnalysisReport) -> Response:
    """분석 JSON을 한글 PDF로 렌더링해 다운로드한다."""

    from services.analyzer.pdf_report import PdfFontError, render_analysis_pdf

    try:
        payload = await asyncio.to_thread(render_analysis_pdf, report)
    except PdfFontError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDF를 만들지 못했습니다. ({exc})") from exc

    filename = f"{report.report_id}.pdf"
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@api.get("/logs/report/{report_id}/pdf")
def download_saved_report_pdf(report_id: str) -> FileResponse:
    """분석 시 Discovery에 저장된 PDF를 내려받는다."""

    if "/" in report_id or "\\" in report_id or ".." in report_id:
        raise HTTPException(status_code=400, detail="잘못된 리포트 ID입니다.")
    repo = Path(__file__).resolve().parents[2]
    path = repo / "knowledge" / "03_Discovery" / "06_Troubleshooting" / f"{report_id}.pdf"
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="저장된 PDF가 없습니다. 대시보드에서 다시 내보내거나 로그를 재분석하십시오.",
        )
    return FileResponse(path, media_type="application/pdf", filename=f"{report_id}.pdf")


@api.post("/knowledge/ingest")
def ingest_knowledge(req: IngestRequest):
    state_payload = {
        "doc_id": req.doc_id,
        "title": req.title,
        "raw_content": req.raw_content,
        "category": req.category,
        "triage_notes": None,
        "is_human_verified": req.is_human_verified,
        "final_path": None
    }
    try:
        final_state = agent_app.invoke(state_payload)
        return {
            "status": "success",
            "routed_path": final_state.get("final_path"),
            "verified": final_state.get("is_human_verified"),
            "triage_notes": final_state.get("triage_notes")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api.post("/knowledge/promote")
def promote_knowledge(req: PromoteRequest):
    from services.knowledge.vault import promote_discovery

    try:
        result = promote_discovery(req.doc_id, req.category)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return result
