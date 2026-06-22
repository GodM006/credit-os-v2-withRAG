"""
AppState = the "Shared Working Memory" box in the architecture diagram.

It's a single LangGraph state object that every agent (in every layer) reads
from and appends to. Layer 1 only touches `source_jsons` and `audit_trail`;
the other fields are reserved for Layers 2-6 so this object doesn't need to
change shape as we build forward.

Why TypedDict + Annotated reducers: LangGraph runs the six Layer 1 agents in
parallel (fan-out from START). When multiple nodes return updates in the same
"superstep", LangGraph needs to know how to merge them. Annotated[...] tells it
to use our reducer function instead of overwriting.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict


def merge_dicts(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    """Shallow-merge two dicts; used so parallel agents can each write their
    own key (e.g. 'banking', 'gst') into source_jsons without clobbering
    each other."""
    merged = dict(left or {})
    merged.update(right or {})
    return merged


class AppState(TypedDict, total=False):
    case_id: str
    company_name: str
    scenario: str

    # Raw synthetic "documents" fed into Layer 1, keyed by source name.
    raw_docs: Dict[str, str]

    # Layer 1 output: one ExtractionResult (as dict) per source.
    source_jsons: Annotated[Dict[str, Any], merge_dicts]

    # Reserved for Layer 2 (Context Graph)
    trust_weights: Annotated[Dict[str, Any], merge_dicts]

    # Reserved for Layer 3 (Triangulation Engine)
    fraud_signals: Annotated[List[Any], operator.add]
    contradictions: Annotated[List[Any], operator.add]
    effective_metrics: Annotated[Dict[str, Any], merge_dicts]

    # Reserved for Layer 4 (Policy Engine)
    policy_flags: Annotated[List[Any], operator.add]
    policy_summary: Annotated[Dict[str, Any], merge_dicts]

    # Reserved for Layer 5 (ML Risk Scoring)
    risk_score: Optional[float]
    pd: Optional[float]
    lgd: Optional[float]

    # Reserved for Layer 6 (Sanction / Limit Optimisation)
    recommended_limit: Optional[float]
    credit_memo: Optional[str]

    # Written to by every layer, every agent.
    audit_trail: Annotated[List[Dict[str, Any]], operator.add]
    evidence_map: Annotated[Dict[str, Any], merge_dicts]


def new_case_state(case_id: str, raw_docs: Dict[str, str], company_name: str = "", scenario: str = "") -> AppState:
    return AppState(
        case_id=case_id,
        company_name=company_name,
        scenario=scenario,
        raw_docs=raw_docs,
        source_jsons={},
        trust_weights={},
        fraud_signals=[],
        contradictions=[],
        effective_metrics={},
        policy_flags=[],
        policy_summary={},
        risk_score=None,
        pd=None,
        lgd=None,
        recommended_limit=None,
        credit_memo=None,
        audit_trail=[],
        evidence_map={},
    )
