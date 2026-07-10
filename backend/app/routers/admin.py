from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.graphdb.neo4j_client import run_read, run_write

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/reset-graph")
def reset_graph():
    """Wipe every node and relationship from the Neo4j context graph.

    The graph is a persistent, shared store that accumulates every uploaded
    case. This clears it so a fresh upload starts from an empty graph instead
    of fanning out through all previously written (and interlinked) cases.
    Constraints/indexes are left intact.
    """
    try:
        before = run_read(
            "MATCH (n) RETURN count(n) AS nodes, "
            "count { MATCH ()-[r]->() RETURN r } AS rels"
        )
        run_write("MATCH (n) DETACH DELETE n")
    except Exception as exc:  # surface the DB error instead of a bare 500
        raise HTTPException(status_code=502, detail=f"Failed to reset graph: {exc}")

    row = before[0] if before else {"nodes": 0, "rels": 0}
    return {
        "status": "ok",
        "deleted_nodes": row.get("nodes", 0),
        "deleted_relationships": row.get("rels", 0),
    }
