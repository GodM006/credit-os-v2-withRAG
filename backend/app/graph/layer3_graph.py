"""
Layer 3 graph: Triangulation Engine — EWRT redesign.

Node topology (unchanged):
  START → trust_aggregation → effective_metrics → END
  START → fraud_detection                       → END

What changed:
  - trust_aggregation_node now calls evidence_priors (Layer A + B) inside
    trust_aggregation.py and stores the result so effective_metrics_node
    and fraud_detection_node can consume it without redundant recomputation.
  - effective_metrics_node receives evidence_priors from state and passes
    them into compute_effective_metrics (Layer C + D).
  - fraud_detection_node receives intra_source_flags and
    gst_self_inconsistency_pct from state and passes them into
    detect_fraud_and_contradictions (Layer B signal emission).

All reads/writes still go through AppState reducers — no state shape changes.
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
    source_jsons = state.get("source_jsons", {})

    # aggregate_source_trust_weights now calls evidence_priors internally
    result = aggregate_source_trust_weights(pairwise, source_jsons)

    ep_result = result.get("evidence_priors", {})

    return {
        "trust_weights": {
            "aggregated": result["weights"],
            # Stash evidence_priors so downstream nodes don't recompute
            "evidence_priors": ep_result,
        },
        "audit_trail": [_audit_entry("trust_aggregator", {
            "weights": result["weights"],
            "excluded_sources": ep_result.get("excluded_sources", []),
            "intra_source_flags": ep_result.get("intra_source_flags", []),
            "notes": result.get("notes", []),
        })],
    }


def effective_metrics_node(state: AppState) -> dict:
    pairwise = (state.get("trust_weights") or {}).get("pairwise", {})
    aggregated = (state.get("trust_weights") or {}).get("aggregated", {})
    evidence_priors = (state.get("trust_weights") or {}).get("evidence_priors")

    result = compute_effective_metrics(
        state.get("source_jsons", {}),
        aggregated,
        pairwise,
        evidence_priors=evidence_priors,
    )

    # Build a compact audit entry (skip triangulation_detail bulk to keep audit lean)
    audit_detail = {k: v for k, v in result.items() if k not in ("notes", "triangulation_detail")}
    if "triangulation_detail" in result:
        td = result["triangulation_detail"]
        audit_detail["confidence_breakdown"] = td.get("confidence_breakdown")
        audit_detail["excluded_sources"] = td.get("excluded_sources")
        audit_detail["intra_source_flags"] = td.get("intra_source_flags")

    return {
        "effective_metrics": result,
        "audit_trail": [_audit_entry("effective_metrics_calculator", audit_detail)],
    }


def fraud_detection_node(state: AppState) -> dict:
    pairwise = (state.get("trust_weights") or {}).get("pairwise", {})
    cin = (state.get("evidence_map") or {}).get("graph_write", {}).get("company_cin")

    # Pull Layer B outputs computed by trust_aggregation_node
    ep_result = (state.get("trust_weights") or {}).get("evidence_priors") or {}
    intra_source_flags = ep_result.get("intra_source_flags", [])
    gst_self_inconsistency_pct = ep_result.get("gst_self_inconsistency_pct")

    related_parties, shared_accounts = [], []
    graph_check_note = None
    if cin:
        try:
            related_parties = find_related_parties(cin)
            shared_accounts = find_shared_bank_accounts(cin)
        except Exception as e:
            graph_check_note = f"Neo4j traversal failed: {e}"
    else:
        graph_check_note = "Layer 2 hasn't been run for this case — graph-based fraud checks skipped."

    result = detect_fraud_and_contradictions(
        state.get("source_jsons", {}),
        pairwise,
        related_parties,
        shared_accounts,
        intra_source_flags=intra_source_flags,
        gst_self_inconsistency_pct=gst_self_inconsistency_pct,
    )
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
            "intra_source_flags": intra_source_flags,
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
