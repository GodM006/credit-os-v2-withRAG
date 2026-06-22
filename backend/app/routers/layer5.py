from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app import store
from app.graph.layer5_graph import layer5_app
from app.ml.inference import _get_model

router = APIRouter(prefix="/api/layer5", tags=["layer5"])


@router.get("/model-info")
def model_info():
    """Returns metadata about the currently loaded risk model."""
    try:
        bundle = _get_model()
        return {
            "model_name": bundle.get("model_name"),
            "trained_on": "synthetic" if bundle.get("n_rows") else "unknown",
            "n_training_rows": bundle.get("n_rows"),
            "model_path": str(__import__("app.ml.trainer", fromlist=["MODEL_PATH"]).MODEL_PATH),
            "status": "loaded",
        }
    except Exception as e:
        return {"status": "not_loaded", "error": str(e)}


@router.post("/cases/{case_id}/run")
def run_layer5(case_id: str):
    """Run the ML risk scoring model on a case's extracted and reconciled features."""
    state = store.get_case(case_id)
    if state is None:
        raise HTTPException(status_code=404, detail="case not found")
    if not state.get("effective_metrics"):
        raise HTTPException(status_code=409, detail="Run Layer 3 first — ML scoring needs effective_metrics.")

    result_state = layer5_app.invoke(state)
    store.save_case(case_id, dict(result_state))
    return result_state
