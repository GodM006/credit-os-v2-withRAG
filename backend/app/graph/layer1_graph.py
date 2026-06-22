"""
Layer 1 graph: Data Acquisition Agents.

All six agents are independent of each other (banking doesn't need GST's
output, etc.) so we fan them out from START in parallel and let LangGraph's
reducers (see app/state.py) merge their writes back into one AppState.
"""
from __future__ import annotations

from datetime import datetime, timezone

from langgraph.graph import END, START, StateGraph

from app.agents import (
    banking_agent,
    bureau_agent,
    financials_agent,
    gst_agent,
    kyc_agent,
    ledger_agent,
)
from app.state import AppState


def _audit_entry(source: str, result_dict: dict) -> dict:
    return {
        "layer": 1,
        "agent": source,
        "validation_status": result_dict.get("validation_status"),
        "confidence": result_dict.get("confidence"),
        "attempts": result_dict.get("attempts"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def banking_node(state: AppState) -> dict:
    result = banking_agent.run(state["raw_docs"].get("banking", ""))
    d = result.model_dump(mode="json")
    return {"source_jsons": {"banking": d}, "audit_trail": [_audit_entry("banking", d)]}


def gst_node(state: AppState) -> dict:
    result = gst_agent.run(state["raw_docs"].get("gst", ""))
    d = result.model_dump(mode="json")
    return {"source_jsons": {"gst": d}, "audit_trail": [_audit_entry("gst", d)]}


def bureau_node(state: AppState) -> dict:
    result = bureau_agent.run(state["raw_docs"].get("bureau", ""))
    d = result.model_dump(mode="json")
    return {"source_jsons": {"bureau": d}, "audit_trail": [_audit_entry("bureau", d)]}


def financials_node(state: AppState) -> dict:
    result = financials_agent.run(state["raw_docs"].get("financials", ""))
    d = result.model_dump(mode="json")
    return {"source_jsons": {"financials": d}, "audit_trail": [_audit_entry("financials", d)]}


def ledger_node(state: AppState) -> dict:
    result = ledger_agent.run(state["raw_docs"].get("ledger", ""))
    d = result.model_dump(mode="json")
    return {"source_jsons": {"ledger": d}, "audit_trail": [_audit_entry("ledger", d)]}


def kyc_node(state: AppState) -> dict:
    result = kyc_agent.run(state["raw_docs"].get("kyc", ""))
    d = result.model_dump(mode="json")
    return {"source_jsons": {"kyc": d}, "audit_trail": [_audit_entry("kyc", d)]}


def build_layer1_graph():
    graph = StateGraph(AppState)

    nodes = {
        "banking": banking_node,
        "gst": gst_node,
        "bureau": bureau_node,
        "financials": financials_node,
        "ledger": ledger_node,
        "kyc": kyc_node,
    }
    for name, fn in nodes.items():
        graph.add_node(name, fn)
        graph.add_edge(START, name)
        graph.add_edge(name, END)

    return graph.compile()


layer1_app = build_layer1_graph()
