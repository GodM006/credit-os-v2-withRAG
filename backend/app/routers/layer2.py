from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app import store
from app.graph.layer2_graph import layer2_app
from app.graphdb import queries
from app.graphdb.neo4j_client import verify_connectivity

router = APIRouter(prefix="/api/layer2", tags=["layer2"])


def _get_company_cin(case_id: str) -> str:
    state = store.get_case(case_id)
    if state is None:
        raise HTTPException(status_code=404, detail="case not found")
    cin = (state.get("evidence_map") or {}).get("graph_write", {}).get("company_cin")
    if not cin:
        raise HTTPException(
            status_code=409,
            detail="Layer 2 hasn't been run for this case yet (no company_cin on record). POST /run first.",
        )
    return cin


@router.get("/health")
def neo4j_health():
    return {"neo4j_reachable": verify_connectivity()}


@router.post("/cases/{case_id}/run")
def run_layer2(case_id: str):
    """Write source_jsons into Neo4j + compute pairwise trust weights."""
    state = store.get_case(case_id)
    if state is None:
        raise HTTPException(status_code=404, detail="case not found")
    if not state.get("source_jsons"):
        raise HTTPException(status_code=409, detail="Run Layer 1 on this case first - no source_jsons present.")

    try:
        result_state = layer2_app.invoke(state)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Layer 2 run failed (is Neo4j reachable?): {e}")

    store.save_case(case_id, dict(result_state))
    return result_state


@router.get("/cases/{case_id}/graph")
def get_case_graph(case_id: str):
    cin = _get_company_cin(case_id)
    return queries.get_company_graph(cin)


@router.get("/cases/{case_id}/related-parties")
def get_related_parties(case_id: str):
    cin = _get_company_cin(case_id)
    return {"cin": cin, "related_parties": queries.find_related_parties(cin)}
