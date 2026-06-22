"""
Credit Memo Agent — the one LLM call in Layer 6.

Takes the fully populated AppState and writes a structured credit memo
narrative: applicant profile, financial triangulation summary, risk flags,
policy outcome, ML score interpretation, and the recommended limit with
rationale. Groq / Llama 3.3, same model as Layer 1's extraction agents.

The memo is structured but written as prose — not bullet points — so it
reads like a real credit analyst's write-up that a RM or committee member
can review and sign off on. Template + evidence injection (RAG-lite) pattern
from the diagram: we inject the actual numbers from AppState into the prompt
so the model never hallucinates figures — it can only paraphrase them.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict

from langchain_groq import ChatGroq

from app.config import settings

logger = logging.getLogger(__name__)


def _safe(val: Any, fmt: str = "") -> str:
    if val is None:
        return "not available"
    if fmt == "inr" and isinstance(val, (int, float)):
        return f"Rs {val:,.0f}"
    if fmt == "pct" and isinstance(val, (int, float)):
        return f"{val * 100:.1f}%"
    return str(val)


def _build_evidence_block(state: Dict[str, Any]) -> str:
    src = state.get("source_jsons", {})
    em = state.get("effective_metrics", {})
    ps = state.get("policy_summary", {})
    kyc = (src.get("kyc") or {}).get("data") or {}
    gst = (src.get("gst") or {}).get("data") or {}
    bureau = (src.get("bureau") or {}).get("data") or {}
    financials = (src.get("financials") or {}).get("data") or {}
    ledger = (src.get("ledger") or {}).get("data") or {}

    fraud_signals = state.get("fraud_signals", [])
    signal_summary = "; ".join(
        f"{s['type']} ({s['severity']}): {s['message']}" for s in fraud_signals
    ) or "None detected"

    failed_rules = ps.get("failed_rules", [])

    evidence = {
        "company_name": kyc.get("legal_name") or state.get("company_name"),
        "entity_type": kyc.get("entity_type"),
        "incorporation_date": kyc.get("incorporation_date"),
        "directors": [d.get("name") for d in (kyc.get("directors") or [])],
        "gstin": gst.get("gstin"),
        "gst_vintage_months": gst.get("vintage_months"),
        "gst_filing_status": gst.get("filing_status"),
        "bureau_score": bureau.get("bureau_score"),
        "dpd_90_plus": bureau.get("dpd_90_plus"),
        "written_off_accounts": bureau.get("written_off_accounts"),
        "total_bureau_exposure_inr": bureau.get("total_exposure"),
        "revenue_inr": financials.get("revenue"),
        "ebitda_inr": financials.get("ebitda"),
        "net_worth_inr": financials.get("net_worth"),
        "debt_equity_ratio": financials.get("debt_equity_ratio"),
        "debtor_days": ledger.get("debtor_days"),
        "creditor_days": ledger.get("creditor_days"),
        "anchor_concentration_pct": ledger.get("top_debtor_concentration_pct"),
        "effective_turnover_inr": em.get("effective_turnover"),
        "confidence": em.get("confidence"),
        "working_capital_gap_inr": em.get("working_capital_gap"),
        "repayment_capacity_inr": em.get("repayment_capacity"),
        "current_dscr": em.get("current_dscr"),
        "fraud_risk": em.get("fraud_risk"),
        "fraud_signals": signal_summary,
        "policy_decision": ps.get("policy_decision"),
        "failed_policy_rules": failed_rules,
        "rule_pass_rate_pct": ps.get("rule_pass_rate"),
        "risk_score_out_of_83": state.get("risk_score"),
        "pd_pct": round(state["pd"] * 100, 2) if state.get("pd") is not None else None,
        "lgd_pct": round(state["lgd"] * 100, 1) if state.get("lgd") is not None else None,
        "risk_band": em.get("risk_band"),
        "recommended_limit_inr": state.get("recommended_limit"),
        "binding_constraint": (state.get("evidence_map") or {}).get("limit_optimiser", {}).get("binding_constraint"),
    }
    return json.dumps(evidence, indent=2, default=str)


MEMO_SYSTEM_PROMPT = """\
You are a senior credit analyst writing an internal credit memo for a working capital loan application.
You will be given a JSON evidence block containing all the verified data from the credit underwriting pipeline.
Write a structured credit memo with the following sections, each as a short paragraph (3-5 sentences):
1. Applicant Profile
2. Financial Triangulation & Confidence
3. Risk Flags & Fraud Assessment
4. Policy & Compliance Outcome
5. Risk Score & Credit Quality
6. Recommended Limit & Rationale

Rules:
- Use ONLY the numbers from the evidence block. Do not invent or estimate any figure not present.
- Write in professional banking prose (not bullet points).
- If a field says "not available", acknowledge the gap honestly.
- Use Indian number formatting (lakhs/crores) for INR amounts above Rs 1,00,000.
- End with a one-line "Recommendation:" sentence stating the limit and any conditions.
"""


def generate_credit_memo(state: Dict[str, Any]) -> str:
    evidence = _build_evidence_block(state)

    llm = ChatGroq(
        model=settings.GROQ_MODEL,
        api_key=settings.GROQ_API_KEY,
        temperature=0.2,
        max_tokens=1200,
    )

    messages = [
        {"role": "system", "content": MEMO_SYSTEM_PROMPT},
        {"role": "user", "content": f"Evidence block:\n{evidence}\n\nWrite the credit memo now."},
    ]

    try:
        response = llm.invoke(messages)
        return response.content if isinstance(response.content, str) else str(response.content)
    except Exception as e:
        logger.error("Credit memo generation failed: %s", e)
        return f"[Credit memo generation failed: {e}]"
