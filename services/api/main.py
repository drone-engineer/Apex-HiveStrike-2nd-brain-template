import sys
import os
import shutil
import asyncio
import tempfile
from pathlib import Path
from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel
from typing import Optional

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))
from services.agent.graph import app as agent_app
from services.analyzer.schemas import AnalysisReport
from services.analyzer.ulog_analyzer import ULogAnalyzer, ULogParseError

api = FastAPI(
    title="Apex HiveStrike Drone Agent API",
    description="2nd-Brain 지식 파이프라인, 승격 백엔드, ULog 이상 진단 API",
    version="0.4.0"
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
    return {"status": "online", "service": "Apex HiveStrike Core", "version": "0.4.0"}


@api.post("/logs/analyze", response_model=AnalysisReport)
async def analyze_flight_log(
    file: UploadFile = File(..., description="PX4 ULog (.ulg) 파일"),
    save_report: bool = True,
) -> AnalysisReport:
    """업로드된 .ulg를 파싱해 진동/EKF2/전압 이상을 진단하고 Canonical 처방 리포트를 반환한다."""

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
