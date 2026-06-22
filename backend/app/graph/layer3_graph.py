"""
Layer 3 graph: Triangulation Engine.

Two branches from START:
  - trust_aggregation -> effective_metrics   (sequential: the second node
    needs the first's aggregated weights, which is why this isn't fanned out
    like Layer 1/2)
  - fraud_detection                          (independent: only needs
    source_jsons + Layer 2's pairwise weights + a Neo4j read)

Both branches read from AppState and write back into it via the same
reducers used in Layers 1-2, so nothing about the state shape changes.
"""
from __future__ import annotations

from datetime import datetime, timezone

from langgraph.graph import END, START, StateGraph

from app.graphdb.queries import find_related_parties, find_shared_bank_accounts
from app.layer3.effective_metrics import compute_effective_metrics
from app.layer3.fraud_signals import detect_fraud_and_contradictions
from app.layer3.trust_aggregation import aggregate_source_trust_weights
from app.state import AppState


def _audit_entry(agent: str, detail: dict) -> dict:
    return {"layer": 3, "agent": agent, "detail": detail, "timestamp": datetime.now(timezone.utc).isoformat()}


def trust_aggregation_node(state: AppState) -> dict:
    pairwise = (state.get("trust_weights") or {}).get("pairwise", {})
    result = aggregate_source_trust_weights(pairwise)
    return {
        "trust_weights": {"aggregated": result["weights"]},
        "audit_trail": [_audit_entry("trust_aggregator", result)],
    }


def effective_metrics_node(state: AppState) -> dict:
    pairwise = (state.get("trust_weights") or {}).get("pairwise", {})
    aggregated = (state.get("trust_weights") or {}).get("aggregated", {})
    result = compute_effective_metrics(state.get("source_jsons", {}), aggregated, pairwise)
    return {
        "effective_metrics": result,
        "audit_trail": [_audit_entry("effective_metrics_calculator", {k: v for k, v in result.items() if k != "notes"})],
    }


def fraud_detection_node(state: AppState) -> dict:
    pairwise = (state.get("trust_weights") or {}).get("pairwise", {})
    cin = (state.get("evidence_map") or {}).get("graph_write", {}).get("company_cin")

    related_parties, shared_accounts = [], []
    graph_check_note = None
    if cin:
        try:
            related_parties = find_related_parties(cin)
            shared_accounts = find_shared_bank_accounts(cin)
        except Exception as e:
            graph_check_note = f"Neo4j traversal failed: {e}"
    else:
        graph_check_note = "Layer 2 hasn't been run for this case - graph-based fraud checks skipped."

    result = detect_fraud_and_contradictions(state.get("source_jsons", {}), pairwise, related_parties, shared_accounts)
    if graph_check_note:
        result["graph_check_note"] = graph_check_note

    return {
        "fraud_signals": result["fraud_signals"],
        "contradictions": result["contradictions"],
        "effective_metrics": {"fraud_risk": result["fraud_risk"]},
        "audit_trail": [_audit_entry("fraud_detector", {
            "fraud_risk": result["fraud_risk"],
            "signal_count": len(result["fraud_signals"]),
            "contradiction_count": len(result["contradictions"]),
        })],
    }


def build_layer3_graph():
    graph = StateGraph(AppState)
    graph.add_node("trust_aggregation", trust_aggregation_node)
    graph.add_node("effective_metrics", effective_metrics_node)
    graph.add_node("fraud_detection", fraud_detection_node)

    graph.add_edge(START, "trust_aggregation")
    graph.add_edge("trust_aggregation", "effective_metrics")
    graph.add_edge("effective_metrics", END)

    graph.add_edge(START, "fraud_detection")
    graph.add_edge("fraud_detection", END)

    return graph.compile()


layer3_app = build_layer3_graph()
