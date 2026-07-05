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
from app.layer1.rag import retrieve_relevant_context
from app.layer1.graph_rag import get_entity_context


def _enrich_with_graph(state: AppState, retrieved_text: str) -> str:
    """Prepend Neo4j entity context to the retrieved document text if available."""
    cin = state.get("company_cin")  # type: ignore[arg-type]
    if not cin:
        return retrieved_text
    graph_ctx = get_entity_context(cin)
    if not graph_ctx:
        return retrieved_text
    return f"{graph_ctx}\n\n{retrieved_text}"


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
    raw_text = state["raw_docs"].get("banking", "")
    retrieved_text = retrieve_relevant_context("banking", raw_text)
    retrieved_text = _enrich_with_graph(state, retrieved_text)
    result = banking_agent.run(retrieved_text)
    d = result.model_dump(mode="json")
    return {"source_jsons": {"banking": d}, "audit_trail": [_audit_entry("banking", d)]}


def gst_node(state: AppState) -> dict:
    raw_text = state["raw_docs"].get("gst", "")
    retrieved_text = retrieve_relevant_context("gst", raw_text)
    retrieved_text = _enrich_with_graph(state, retrieved_text)
    result = gst_agent.run(retrieved_text)
    d = result.model_dump(mode="json")
    return {"source_jsons": {"gst": d}, "audit_trail": [_audit_entry("gst", d)]}


def bureau_node(state: AppState) -> dict:
    raw_text = state["raw_docs"].get("bureau", "")
    retrieved_text = retrieve_relevant_context("bureau", raw_text)
    retrieved_text = _enrich_with_graph(state, retrieved_text)
    result = bureau_agent.run(retrieved_text)
    d = result.model_dump(mode="json")
    return {"source_jsons": {"bureau": d}, "audit_trail": [_audit_entry("bureau", d)]}


def financials_node(state: AppState) -> dict:
    raw_text = state["raw_docs"].get("financials", "")
    retrieved_text = retrieve_relevant_context("financials", raw_text)
    retrieved_text = _enrich_with_graph(state, retrieved_text)
    result = financials_agent.run(retrieved_text)
    d = result.model_dump(mode="json")
    return {"source_jsons": {"financials": d}, "audit_trail": [_audit_entry("financials", d)]}


def ledger_node(state: AppState) -> dict:
    raw_text = state["raw_docs"].get("ledger", "")
    retrieved_text = retrieve_relevant_context("ledger", raw_text)
    retrieved_text = _enrich_with_graph(state, retrieved_text)
    result = ledger_agent.run(retrieved_text)
    d = result.model_dump(mode="json")
    return {"source_jsons": {"ledger": d}, "audit_trail": [_audit_entry("ledger", d)]}


def kyc_node(state: AppState) -> dict:
    raw_text = state["raw_docs"].get("kyc", "")
    retrieved_text = retrieve_relevant_context("kyc", raw_text)
    retrieved_text = _enrich_with_graph(state, retrieved_text)
    result = kyc_agent.run(retrieved_text)
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
