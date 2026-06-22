"""
Layer 5 graph: ML Risk Scoring Agent.

Single node. Runs inference on the pre-trained LightGBM/LR model using
features extracted from AppState. Writes pd, risk_score, lgd into AppState
(all three are first-class fields in the state schema, reserved from day 1).
"""
from __future__ import annotations

from datetime import datetime, timezone

from langgraph.graph import END, START, StateGraph

from app.ml.inference import run_inference
from app.state import AppState


def _audit_entry(detail: dict) -> dict:
    return {
        "layer": 5,
        "agent": "ml_risk_scorer",
        "detail": detail,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def ml_scoring_node(state: AppState) -> dict:
    result = run_inference(dict(state))

    return {
        "risk_score": result["risk_score"],
        "pd": result["pd"],
        "lgd": result["lgd"],
        "effective_metrics": {
            "risk_band": result["risk_band"],
            "expected_loss_rate": result["expected_loss_rate"],
            "ml_model_name": result["model_name"],
            "ml_trained_on": result["trained_on"],
        },
        "audit_trail": [
            _audit_entry(
                {
                    "risk_score": result["risk_score"],
                    "pd": result["pd"],
                    "lgd": result["lgd"],
                    "risk_band": result["risk_band"],
                    "model": result["model_name"],
                }
            )
        ],
    }


def build_layer5_graph():
    graph = StateGraph(AppState)
    graph.add_node("ml_risk_scorer", ml_scoring_node)
    graph.add_edge(START, "ml_risk_scorer")
    graph.add_edge("ml_risk_scorer", END)
    return graph.compile()


layer5_app = build_layer5_graph()
