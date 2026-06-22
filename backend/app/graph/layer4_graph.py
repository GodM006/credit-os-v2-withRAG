"""
Layer 4 graph: Policy Engine / BRE.

Single node - all five rules evaluate the same inputs and have no internal
dependency on each other, so there's no benefit to fanning them out. One
Pydantic-validated function call, result written into AppState.policy_summary
and policy_flags (one entry per failed rule, matching the diagram's
policy_flags list).
"""
from __future__ import annotations

from datetime import datetime, timezone

from langgraph.graph import END, START, StateGraph

from app.layer4.rules import evaluate_policy
from app.state import AppState


def _audit_entry(detail: dict) -> dict:
    return {
        "layer": 4,
        "agent": "policy_bre",
        "detail": detail,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def policy_node(state: AppState) -> dict:
    source_jsons = state.get("source_jsons", {})
    effective_metrics = state.get("effective_metrics", {})

    result = evaluate_policy(source_jsons, effective_metrics)

    policy_flags = [
        {
            "rule_id": r["rule_id"],
            "label": r["label"],
            "value": r["value"],
            "threshold": r["threshold"],
            "note": r.get("note", ""),
        }
        for r in result["rule_results"]
        if not r["passed"]
    ]

    return {
        "policy_summary": {
            "policy_decision": result["policy_decision"],
            "rule_pass_rate": result["rule_pass_rate"],
            "deviation_flag": result["deviation_flag"],
            "failed_rules": result["failed_rules"],
            "passed_rules": result["passed_rules"],
            "total_rules": result["total_rules"],
            "rule_results": result["rule_results"],
        },
        "policy_flags": policy_flags,
        "audit_trail": [
            _audit_entry(
                {
                    "policy_decision": result["policy_decision"],
                    "rule_pass_rate": result["rule_pass_rate"],
                    "failed_rules": result["failed_rules"],
                }
            )
        ],
    }


def build_layer4_graph():
    graph = StateGraph(AppState)
    graph.add_node("policy_bre", policy_node)
    graph.add_edge(START, "policy_bre")
    graph.add_edge("policy_bre", END)
    return graph.compile()


layer4_app = build_layer4_graph()
