from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app import store
from app.graph.layer6_graph import layer6_app
from app.layer6.cam_builder import build_cam
from app.layer6.cam_docx import generate_cam_docx
from app.layer6.cam_pdf import generate_cam_pdf

router = APIRouter(prefix="/api/layer6", tags=["layer6"])


def _get_complete_state(case_id: str) -> dict:
    state = store.get_case(case_id)
    if state is None:
        raise HTTPException(status_code=404, detail="case not found")
    if not state.get("credit_memo"):
        raise HTTPException(
            status_code=409,
            detail="Run Layer 6 first — CAM download requires a completed credit memo.",
        )
    return state


@router.post("/cases/{case_id}/run")
def run_layer6(case_id: str):
    """Compute recommended limit (5 constraints) and generate LLM credit memo."""
    state = store.get_case(case_id)
    if state is None:
        raise HTTPException(status_code=404, detail="case not found")
    if not state.get("effective_metrics"):
        raise HTTPException(status_code=409, detail="Run Layer 3 first.")
    if not state.get("policy_summary"):
        raise HTTPException(status_code=409, detail="Run Layer 4 first.")

    result_state = layer6_app.invoke(state)
    store.save_case(case_id, dict(result_state))
    return result_state


@router.get("/cases/{case_id}/memo")
def get_memo(case_id: str):
    """Return just the credit memo text for a completed case."""
    state = store.get_case(case_id)
    if state is None:
        raise HTTPException(status_code=404, detail="case not found")
    memo = state.get("credit_memo")
    if not memo:
        raise HTTPException(status_code=409, detail="Layer 6 hasn't been run yet.")
    return {"case_id": case_id, "credit_memo": memo}


@router.get("/cases/{case_id}/download/cam.docx")
def download_cam_docx(case_id: str):
    """Download the full Credit Appraisal Memorandum as a .docx file."""
    state = _get_complete_state(case_id)
    cam = build_cam(state)
    buf = generate_cam_docx(cam, analyst_narrative=state.get("credit_memo", ""))
    company = (cam["meta"]["company_name"] or case_id).replace(" ", "_")[:40]
    filename = f"CAM_{company}_{case_id}.docx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/cases/{case_id}/download/cam.pdf")
def download_cam_pdf(case_id: str):
    """Download the full Credit Appraisal Memorandum as a .pdf file."""
    state = _get_complete_state(case_id)
    cam = build_cam(state)
    buf = generate_cam_pdf(cam, analyst_narrative=state.get("credit_memo", ""))
    company = (cam["meta"]["company_name"] or case_id).replace(" ", "_")[:40]
    filename = f"CAM_{company}_{case_id}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
