from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app import store
from app.graph.layer4_graph import layer4_app

router = APIRouter(prefix="/api/layer4", tags=["layer4"])


@router.post("/cases/{case_id}/run")
def run_layer4(case_id: str):
    """Evaluate all 5 hard eligibility rules against Layer 3's effective_metrics
    and Layer 1's extracted source data. Returns policy_decision, rule_pass_rate,
    and per-rule results."""
    state = store.get_case(case_id)
    if state is None:
        raise HTTPException(status_code=404, detail="case not found")
    if not state.get("source_jsons"):
        raise HTTPException(status_code=409, detail="Run Layer 1 first.")
    if not state.get("effective_metrics"):
        raise HTTPException(status_code=409, detail="Run Layer 3 first — policy rules need effective_metrics (DSCR etc.).")

    result_state = layer4_app.invoke(state)
    store.save_case(case_id, dict(result_state))
    return result_state
