"""
Fraud/contradiction detection for Layer 3.

Two distinct kinds of output, deliberately kept separate:
  - contradictions: objective numeric disagreements between sources (no
    claim of intent) - surfaced from Layer 2's pairwise variances.
  - fraud_signals: pattern-based risk flags, each with a severity. Some come
    straight from one source's data (high cash deposits, bureau write-offs),
    others require a graph traversal in Neo4j (related parties, shared bank
    accounts) - this is the "Fraud: Neo4j traversal" line from the diagram.

fraud_risk is then a simple roll-up: any "high" severity signal -> high;
else any "medium" -> medium; else low.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

CONTRADICTION_THRESHOLD = 0.15  # variance_pct above which we call it out as a real contradiction

PAIR_LABELS = {
    "gst_vs_bank": "GST-reported turnover vs bank-inferred turnover",
    "bank_vs_financials": "Bank-inferred turnover vs financial statement revenue",
    "gst_vs_ledger": "GST-reported turnover vs ledger sales",
}


def _signal(type_: str, severity: str, message: str, evidence: Optional[dict] = None) -> dict:
    return {"type": type_, "severity": severity, "message": message, "evidence": evidence or {}}


def detect_fraud_and_contradictions(
    source_jsons: Dict[str, Any],
    pairwise: Dict[str, Any],
    related_parties: List[Dict[str, Any]],
    shared_bank_accounts: List[Dict[str, Any]],
    intra_source_flags: Optional[List[str]] = None,
    gst_self_inconsistency_pct: Optional[float] = None,
) -> Dict[str, Any]:
    contradictions: List[dict] = []
    signals: List[dict] = []

    # --- Contradictions from Layer 2's pairwise variances ---
    for key, pair in pairwise.items():
        if pair["variance_pct"] > CONTRADICTION_THRESHOLD:
            contradictions.append(
                {
                    "pair": key,
                    "message": f"{PAIR_LABELS.get(key, key)} differ by {pair['variance_pct']*100:.1f}%",
                    "value_a": pair["value_a"],
                    "value_b": pair["value_b"],
                    "variance_pct": pair["variance_pct"],
                }
            )

    banking = (source_jsons.get("banking") or {}).get("data")
    gst = (source_jsons.get("gst") or {}).get("data")
    bureau = (source_jsons.get("bureau") or {}).get("data")
    ledger = (source_jsons.get("ledger") or {}).get("data")

    # --- Layer B: intra-source self-consistency flags (from evidence_priors) ---
    if intra_source_flags and "gst_self_inconsistent" in intra_source_flags:
        pct_str = f" ({gst_self_inconsistency_pct*100:.1f}%)" if gst_self_inconsistency_pct is not None else ""
        signals.append(_signal(
            "gst_self_inconsistent", "medium",
            f"GSTR-3B and GSTR-1 annual turnovers are internally inconsistent{pct_str} — "
            "a known GST compliance/fraud indicator where the monthly summary does not match the sales register",
            {
                "gstr3b_annual_turnover": gst.get("gstr3b_annual_turnover") if gst else None,
                "gstr1_annual_turnover": gst.get("gstr1_annual_turnover") if gst else None,
                "divergence_pct": gst_self_inconsistency_pct,
            },
        ))

    # --- Source-level red flags ---
    if banking:
        ratio = banking.get("cash_deposit_ratio")
        if ratio is not None and ratio > 0.30:
            signals.append(_signal(
                "high_cash_deposits", "high" if ratio > 0.45 else "medium",
                f"Cash deposits are {ratio*100:.0f}% of total credits - possible turnover inflation",
                {"cash_deposit_ratio": ratio},
            ))
        if banking.get("bounce_count") is not None and int(banking["bounce_count"]) > 5:
            signals.append(_signal(
                "excessive_bounces", "medium",
                f"{banking['bounce_count']} cheque/ECS bounces in the period",
                {"bounce_count": banking["bounce_count"]},
            ))

    gst_vs_bank = pairwise.get("gst_vs_bank")
    if gst_vs_bank and gst_vs_bank["trust_weight"] < 0.5 and gst_vs_bank["value_b"] > gst_vs_bank["value_a"]:
        # bank-inferred turnover well above GST-declared turnover: classic
        # "bank statement window-dressing" pattern (credits that never show
        # up as declared sales).
        signals.append(_signal(
            "turnover_inflation", "high",
            "Bank-inferred turnover substantially exceeds GST-declared turnover",
            {"gst_turnover": gst_vs_bank["value_a"], "bank_turnover": gst_vs_bank["value_b"], "variance_pct": gst_vs_bank["variance_pct"]},
        ))

    if gst and gst.get("filing_status") in ("defaulter", "cancelled", "suspended"):
        signals.append(_signal(
            "gst_compliance_risk", "medium" if gst["filing_status"] != "cancelled" else "high",
            f"GST registration status is '{gst['filing_status']}'",
            {"filing_status": gst["filing_status"]},
        ))

    if bureau:
        if bureau.get("written_off_accounts") is not None and int(bureau["written_off_accounts"]) > 0:
            signals.append(_signal(
                "bureau_write_off", "high",
                f"{bureau['written_off_accounts']} written-off account(s) on bureau record",
                {"written_off_accounts": bureau["written_off_accounts"]},
            ))
        elif bureau.get("dpd_90_plus") is not None and int(bureau["dpd_90_plus"]) > 0:
            signals.append(_signal(
                "bureau_severe_delinquency", "medium",
                f"{bureau['dpd_90_plus']} account(s) at 90+ days past due",
                {"dpd_90_plus": bureau["dpd_90_plus"]},
            ))

    if ledger and ledger.get("top_debtor_concentration_pct") is not None and float(ledger["top_debtor_concentration_pct"]) > 70:
        signals.append(_signal(
            "anchor_concentration", "medium",
            f"Single debtor accounts for {float(ledger['top_debtor_concentration_pct']):.0f}% of receivables",
            {"top_debtor_concentration_pct": ledger["top_debtor_concentration_pct"]},
        ))

    # --- Graph-traversal signals (Neo4j) ---
    if related_parties:
        names = ", ".join(rp["legal_name"] for rp in related_parties)
        signals.append(_signal(
            "related_party_exposure", "medium",
            f"Shares a director with: {names}",
            {"related_parties": related_parties},
        ))

    if shared_bank_accounts:
        names = ", ".join(rp["legal_name"] for rp in shared_bank_accounts)
        signals.append(_signal(
            "shared_banking_instrument", "high",
            f"Shares a bank account with a separately-onboarded entity: {names} - possible shell/structuring pattern",
            {"shared_with": shared_bank_accounts},
        ))

    if any(s["severity"] == "high" for s in signals):
        fraud_risk = "high"
    elif any(s["severity"] == "medium" for s in signals):
        fraud_risk = "medium"
    else:
        fraud_risk = "low"

    return {"fraud_signals": signals, "contradictions": contradictions, "fraud_risk": fraud_risk}
