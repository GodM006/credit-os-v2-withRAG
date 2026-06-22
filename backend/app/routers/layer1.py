from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import store
from app.graph.layer1_graph import layer1_app
from app.state import new_case_state
from app.synthetic.generator import generate_case, generate_linked_pair

router = APIRouter(prefix="/api/layer1", tags=["layer1"])


class GenerateCaseRequest(BaseModel):
    scenario: Literal["clean", "noisy", "fraud_risk"] = "clean"


@router.post("/cases")
def create_case(req: GenerateCaseRequest):
    """Generate a synthetic applicant case (6 raw documents) and store it."""
    case = generate_case(scenario=req.scenario)
    state = new_case_state(
        case_id=case["case_id"],
        raw_docs=case["raw_docs"],
        company_name=case["company_name"],
        scenario=case["scenario"],
    )
    store.save_case(case["case_id"], dict(state))
    return state


@router.post("/cases/linked-pair")
def create_linked_pair(req: GenerateCaseRequest):
    """Generate two cases that deliberately share one director - useful for
    demoing Layer 2's related-party detection, which needs a real collision
    to find anything (independently generated cases won't naturally share a DIN)."""
    case_a, case_b = generate_linked_pair(scenario=req.scenario)
    states = []
    for case in (case_a, case_b):
        state = new_case_state(
            case_id=case["case_id"],
            raw_docs=case["raw_docs"],
            company_name=case["company_name"],
            scenario=case["scenario"],
        )
        store.save_case(case["case_id"], dict(state))
        states.append(state)
    return {"case_a": states[0], "case_b": states[1]}


@router.get("/cases")
def list_cases():
    return store.list_cases()


@router.get("/cases/{case_id}")
def get_case(case_id: str):
    state = store.get_case(case_id)
    if state is None:
        raise HTTPException(status_code=404, detail="case not found")
    return state


@router.post("/cases/{case_id}/run")
def run_case(case_id: str):
    """Run the Layer 1 LangGraph pipeline (all 6 agents, in parallel) on a stored case."""
    state = store.get_case(case_id)
    if state is None:
        raise HTTPException(status_code=404, detail="case not found")

    result_state = layer1_app.invoke(state)
    store.save_case(case_id, dict(result_state))
    return result_state
