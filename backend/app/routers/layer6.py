from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app import store
from app.graph.layer6_graph import layer6_app

router = APIRouter(prefix="/api/layer6", tags=["layer6"])


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
