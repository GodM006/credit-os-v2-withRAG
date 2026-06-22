from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app import store
from app.graph.layer3_graph import layer3_app

router = APIRouter(prefix="/api/layer3", tags=["layer3"])


@router.post("/cases/{case_id}/run")
def run_layer3(case_id: str):
    """Aggregate trust weights -> effective metrics, and run fraud/contradiction detection."""
    state = store.get_case(case_id)
    if state is None:
        raise HTTPException(status_code=404, detail="case not found")
    if not state.get("source_jsons"):
        raise HTTPException(status_code=409, detail="Run Layer 1 on this case first.")
    if not (state.get("trust_weights") or {}).get("pairwise"):
        raise HTTPException(status_code=409, detail="Run Layer 2 on this case first - no pairwise trust weights present.")

    result_state = layer3_app.invoke(state)
    store.save_case(case_id, dict(result_state))
    return result_state
