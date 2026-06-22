"""
Layer 6 graph: Sanction / Limit Optimisation + Credit Memo.

Two nodes, fanned out in parallel from START:
  - limit_optimiser : pure Python, fast, no LLM call
  - credit_memo_agent: one Groq call, writes the narrative memo

They're independent (the memo doesn't need the exact limit number, it
references it from AppState which already has everything else), so parallel
is correct. Both write back into AppState via reducers.
"""
from __future__ import annotations

from datetime import datetime, timezone

from langgraph.graph import END, START, StateGraph

from app.layer6.credit_memo import generate_credit_memo
from app.layer6.limit_optimiser import optimise_limit
from app.state import AppState


def _audit(agent: str, detail: dict) -> dict:
    return {"layer": 6, "agent": agent, "detail": detail, "timestamp": datetime.now(timezone.utc).isoformat()}


def limit_optimiser_node(state: AppState) -> dict:
    result = optimise_limit(
        effective_metrics=state.get("effective_metrics", {}),
        policy_summary=state.get("policy_summary", {}),
        risk_score=state.get("risk_score"),
    )
    return {
        "recommended_limit": result["recommended_limit"],
        "evidence_map": {"limit_optimiser": result},
        "audit_trail": [_audit("limit_optimiser", {
            "recommended_limit": result["recommended_limit"],
            "binding_constraint": result["binding_constraint"],
        })],
    }


def credit_memo_node(state: AppState) -> dict:
    memo = generate_credit_memo(dict(state))
    return {
        "credit_memo": memo,
        "audit_trail": [_audit("credit_memo_agent", {"memo_length_chars": len(memo)})],
    }


def build_layer6_graph():
    graph = StateGraph(AppState)
    graph.add_node("limit_optimiser", limit_optimiser_node)
    graph.add_node("credit_memo_agent", credit_memo_node)

    graph.add_edge(START, "limit_optimiser")
    graph.add_edge(START, "credit_memo_agent")
    graph.add_edge("limit_optimiser", END)
    graph.add_edge("credit_memo_agent", END)

    return graph.compile()


layer6_app = build_layer6_graph()
