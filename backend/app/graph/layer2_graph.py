"""
Layer 2 graph: Context Graph (Entity & Relationship Store).

Two independent jobs run in parallel from START:
  - graph_write: project source_jsons into Neo4j (side effect), record a
    summary + node references into AppState.evidence_map
  - trust_weights: compute pairwise turnover variance -> trust weights into
    AppState.trust_weights

Both only read AppState.source_jsons (written by Layer 1), so there's no
ordering dependency between them.
"""
from __future__ import annotations

from datetime import datetime, timezone

from langgraph.graph import END, START, StateGraph

from app.graphdb.writer import write_case_to_graph
from app.layer2.trust_weights import compute_pairwise_trust_weights
from app.state import AppState


def _audit_entry(agent: str, detail: dict) -> dict:
    return {
        "layer": 2,
        "agent": agent,
        "detail": detail,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def graph_write_node(state: AppState) -> dict:
    summary = write_case_to_graph(state["case_id"], state.get("source_jsons", {}))
    return {
        "evidence_map": {"graph_write": summary},
        "audit_trail": [_audit_entry("context_graph_writer", summary)],
    }


def trust_weights_node(state: AppState) -> dict:
    result = compute_pairwise_trust_weights(state.get("source_jsons", {}))
    return {
        "trust_weights": result,
        "audit_trail": [_audit_entry("trust_weight_calculator", {"pairs_computed": list(result["pairwise"].keys())})],
    }


def build_layer2_graph():
    graph = StateGraph(AppState)
    graph.add_node("graph_write", graph_write_node)
    graph.add_node("trust_weights", trust_weights_node)

    graph.add_edge(START, "graph_write")
    graph.add_edge(START, "trust_weights")
    graph.add_edge("graph_write", END)
    graph.add_edge("trust_weights", END)

    return graph.compile()


layer2_app = build_layer2_graph()
