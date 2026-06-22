"""
Layer 4: Policy Engine / BRE.

Five hard eligibility rules straight off the diagram, each evaluated against
data Layer 1-3 already produced - no new extraction needed.

Design choice, stated plainly: if the data a rule needs is missing (an
upstream agent failed to extract it), the rule FAILS rather than being
skipped. Credit policy shouldn't pass an applicant on the absence of
evidence; "we couldn't verify this" is not the same as "this checks out."

Policy decision bands (not in the diagram verbatim, but implied by
deviation_flag existing as a concept at all - a single failure shouldn't be
treated identically to multiple failures):
  - 0 failed rules  -> "clear"               (auto-pass at policy level)
  - 1-2 failed      -> "deviation_required"  (escalate to a human for override)
  - 3+ failed       -> "policy_reject"
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

DSCR_MIN = 1.25
GST_VINTAGE_MIN_MONTHS = 12
BUREAU_SCORE_MIN = 700
ANCHOR_CONCENTRATION_MAX_PCT = 70.0
DEVIATION_BAND_MAX_FAILURES = 2  # 1-2 failures -> deviation_required; 3+ -> reject


def _rule(rule_id: str, label: str, passed: bool, value: Optional[Any], threshold: Any, note: str = "") -> dict:
    return {"rule_id": rule_id, "label": label, "passed": passed, "value": value, "threshold": threshold, "note": note}


def _check_dscr(effective_metrics: Dict[str, Any]) -> dict:
    dscr = effective_metrics.get("current_dscr")
    existing_service = effective_metrics.get("annual_debt_service_existing", 0)
    if dscr is None:
        if not existing_service:
            return _rule("dscr_min", "DSCR > 1.25", True, None, DSCR_MIN, "No existing debt obligations to service - rule not applicable, treated as pass.")
        return _rule("dscr_min", "DSCR > 1.25", False, None, DSCR_MIN, "DSCR could not be computed (missing financials).")
    return _rule("dscr_min", "DSCR > 1.25", dscr > DSCR_MIN, dscr, DSCR_MIN)


def _check_gst_vintage(source_jsons: Dict[str, Any]) -> dict:
    gst = (source_jsons.get("gst") or {}).get("data")
    if not gst:
        return _rule("gst_vintage_min", "GST vintage > 12 months", False, None, GST_VINTAGE_MIN_MONTHS, "GST data missing/invalid.")
    vintage = gst.get("vintage_months")
    return _rule("gst_vintage_min", "GST vintage > 12 months", vintage > GST_VINTAGE_MIN_MONTHS, vintage, GST_VINTAGE_MIN_MONTHS)


def _check_bureau_score(source_jsons: Dict[str, Any]) -> dict:
    bureau = (source_jsons.get("bureau") or {}).get("data")
    if not bureau:
        return _rule("bureau_score_min", "Bureau score > 700", False, None, BUREAU_SCORE_MIN, "Bureau data missing/invalid.")
    score = bureau.get("bureau_score")
    return _rule("bureau_score_min", "Bureau score > 700", score > BUREAU_SCORE_MIN, score, BUREAU_SCORE_MIN)


def _check_max_dpd(source_jsons: Dict[str, Any]) -> dict:
    bureau = (source_jsons.get("bureau") or {}).get("data")
    if not bureau:
        return _rule("max_dpd_30", "Max DPD bucket <= 30 days", False, None, 30, "Bureau data missing/invalid.")
    worse_than_30 = bureau.get("dpd_60", 0) + bureau.get("dpd_90_plus", 0)
    return _rule("max_dpd_30", "Max DPD bucket <= 30 days", worse_than_30 == 0, worse_than_30, 0,
                 "Counts accounts with DPD worse than the 30-day bucket (60/90+).")


def _check_anchor_concentration(source_jsons: Dict[str, Any]) -> dict:
    ledger = (source_jsons.get("ledger") or {}).get("data")
    if not ledger:
        return _rule("anchor_concentration_max", "Anchor concentration < 70%", False, None, ANCHOR_CONCENTRATION_MAX_PCT, "Ledger data missing/invalid.")
    pct = ledger.get("top_debtor_concentration_pct")
    return _rule("anchor_concentration_max", "Anchor concentration < 70%", pct < ANCHOR_CONCENTRATION_MAX_PCT, pct, ANCHOR_CONCENTRATION_MAX_PCT)


def evaluate_policy(source_jsons: Dict[str, Any], effective_metrics: Dict[str, Any]) -> Dict[str, Any]:
    rule_results: List[dict] = [
        _check_dscr(effective_metrics),
        _check_gst_vintage(source_jsons),
        _check_bureau_score(source_jsons),
        _check_max_dpd(source_jsons),
        _check_anchor_concentration(source_jsons),
    ]

    passed = [r for r in rule_results if r["passed"]]
    failed = [r for r in rule_results if not r["passed"]]
    rule_pass_rate = round(100 * len(passed) / len(rule_results)) if rule_results else 0

    if len(failed) == 0:
        policy_decision = "clear"
    elif len(failed) <= DEVIATION_BAND_MAX_FAILURES:
        policy_decision = "deviation_required"
    else:
        policy_decision = "policy_reject"

    return {
        "rule_results": rule_results,
        "rule_pass_rate": rule_pass_rate,
        "failed_rules": [r["label"] for r in failed],
        "deviation_flag": policy_decision == "deviation_required",
        "policy_decision": policy_decision,
        "total_rules": len(rule_results),
        "passed_rules": len(passed),
    }
