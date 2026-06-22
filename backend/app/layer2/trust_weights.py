"""
Pairwise variance computation between independently-sourced turnover figures.

Per the diagram: GST vs Bank, Bank vs Financials, GST vs Ledger -> pairwise
trust weights. This is deliberately pure Python with no DB/LLM dependency -
it's just comparing numbers already sitting in source_jsons - so it's cheap
to re-run and easy to unit test. Layer 3 (Triangulation Engine) will later
aggregate these pairwise weights into a single per-source trust weight
(e.g. average of all pairs a source participates in) and use them to compute
an effective, confidence-weighted turnover figure.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _variance_pct(a: float, b: float) -> float:
    return abs(a - b) / max(a, b, 1)


def _trust_weight(variance_pct: float) -> float:
    """Piecewise mapping from variance -> trust weight (0-1). Tune thresholds
    as you get real-world data; these are reasonable starting defaults for
    SME turnover comparisons."""
    if variance_pct <= 0.05:
        return 0.95
    if variance_pct <= 0.10:
        return 0.85
    if variance_pct <= 0.20:
        return 0.65
    if variance_pct <= 0.35:
        return 0.40
    return 0.20


def _pair(label_a: str, value_a: Optional[float], label_b: str, value_b: Optional[float]) -> Optional[Dict[str, Any]]:
    if value_a is None or value_b is None:
        return None
    variance_pct = round(_variance_pct(value_a, value_b), 4)
    return {
        "label_a": label_a,
        "value_a": value_a,
        "label_b": label_b,
        "value_b": value_b,
        "variance_pct": variance_pct,
        "trust_weight": _trust_weight(variance_pct),
    }


def compute_pairwise_trust_weights(source_jsons: Dict[str, Any]) -> Dict[str, Any]:
    gst = (source_jsons.get("gst") or {}).get("data")
    banking = (source_jsons.get("banking") or {}).get("data")
    financials = (source_jsons.get("financials") or {}).get("data")
    ledger = (source_jsons.get("ledger") or {}).get("data")

    gst_turnover = gst.get("gstr3b_annual_turnover") if gst else None
    bank_turnover = banking.get("inferred_annual_turnover") if banking else None
    financials_revenue = financials.get("revenue") if financials else None
    ledger_sales = ledger.get("total_sales") if ledger else None

    pairwise: Dict[str, Any] = {}
    skipped: list[str] = []

    p = _pair("gst_turnover", gst_turnover, "bank_turnover", bank_turnover)
    if p:
        pairwise["gst_vs_bank"] = p
    else:
        skipped.append("gst_vs_bank (missing gst or banking data)")

    p = _pair("bank_turnover", bank_turnover, "financials_revenue", financials_revenue)
    if p:
        pairwise["bank_vs_financials"] = p
    else:
        skipped.append("bank_vs_financials (missing banking or financials data)")

    p = _pair("gst_turnover", gst_turnover, "ledger_sales", ledger_sales)
    if p:
        pairwise["gst_vs_ledger"] = p
    else:
        skipped.append("gst_vs_ledger (missing gst or ledger data)")

    return {
        "pairwise": pairwise,
        "skipped": skipped,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
