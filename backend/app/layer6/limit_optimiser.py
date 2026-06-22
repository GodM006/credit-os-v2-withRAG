"""
Layer 6: Sanction / Limit Optimisation.

Five constraints from the diagram applied in order, each acting as a ceiling
on the previous result. The final recommended_limit is the minimum across all
of them (not an arbitrary pick — each constraint exists for a different
regulatory/credit-policy reason and all must hold simultaneously).

C1 Policy cap     : max 20% of effective turnover (RBI MSME WC guideline)
C2 WC need        : we only lend what's needed (the computed working_capital_gap)
C3 Repayment cap  : EBITDA-based repayment capacity limits total new debt service
C4 Risk multiplier: risk_score (1-83) scales the limit down for riskier profiles
C5 Exposure hdroom: total new + existing exposure capped at 40% of effective turnover

Risk appetite multiplier mapping (C4):
  Score 75-83 (A) -> 1.00  (full limit)
  Score 60-74 (B) -> 0.85
  Score 40-59 (C) -> 0.65
  Score 20-39 (D) -> 0.40
  Score 1-19  (E) -> 0.20  (or policy_reject overrides entirely)

All amounts in INR. Returns a full trace so the frontend (and audit trail)
can show which constraint was the binding one.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

POLICY_CAP_PCT = 0.20          # C1: 20% of effective turnover
EXPOSURE_HDROOM_PCT = 0.40     # C5: new + existing <= 40% of effective turnover
MIN_LIMIT = 100_000            # floor: don't sanction below Rs 1 lakh

RISK_MULTIPLIERS = [
    (75, 83, 1.00),
    (60, 74, 0.85),
    (40, 59, 0.65),
    (20, 39, 0.40),
    (1,  19, 0.20),
]


def _risk_multiplier(risk_score: Optional[int]) -> float:
    if risk_score is None:
        return 0.65  # conservative default when score isn't available
    for lo, hi, mult in RISK_MULTIPLIERS:
        if lo <= risk_score <= hi:
            return mult
    return 0.65


def optimise_limit(
    effective_metrics: Dict[str, Any],
    policy_summary: Dict[str, Any],
    risk_score: Optional[int],
) -> Dict[str, Any]:
    policy_decision = policy_summary.get("policy_decision", "policy_reject")

    if policy_decision == "policy_reject":
        return {
            "recommended_limit": 0,
            "binding_constraint": "policy_reject",
            "constraints": {},
            "risk_multiplier": 0.0,
            "note": "Policy Engine returned policy_reject — limit is zero.",
        }

    effective_turnover = effective_metrics.get("effective_turnover") or 0
    wc_gap = effective_metrics.get("working_capital_gap") or 0
    repayment_capacity = effective_metrics.get("repayment_capacity") or 0
    existing_exposure = effective_metrics.get("annual_debt_service_existing", 0)

    # annual_debt_service_existing is ~30% of total bureau exposure, so reverse
    # to get the exposure stock for headroom calc
    bureau_total_exposure = existing_exposure / 0.30 if existing_exposure else 0

    c1 = round(effective_turnover * POLICY_CAP_PCT) if effective_turnover else 0
    c2 = round(wc_gap) if wc_gap else c1
    c3 = round(repayment_capacity) if repayment_capacity > 0 else c1

    mult = _risk_multiplier(risk_score)
    running = min(c for c in [c1, c2, c3] if c > 0) if any(c > 0 for c in [c1, c2, c3]) else 0
    c4 = round(running * mult)

    if effective_turnover:
        headroom = max(0, round(effective_turnover * EXPOSURE_HDROOM_PCT - bureau_total_exposure))
    else:
        headroom = c4
    c5 = min(c4, headroom)

    final = max(0, c5)
    if 0 < final < MIN_LIMIT:
        final = 0
        binding = "below_minimum_floor"
    else:
        limits_named = {"C1_policy_cap": c1, "C2_wc_need": c2, "C3_repayment": c3, "C4_risk_adj": c4, "C5_exposure_hdroom": c5}
        binding = min(limits_named, key=lambda k: limits_named[k]) if final > 0 else "zero_inputs"

    if policy_decision == "deviation_required":
        note = "Limit computed under deviation_required — subject to credit committee approval before disbursal."
    else:
        note = "Limit cleared all policy and constraint checks."

    return {
        "recommended_limit": final,
        "binding_constraint": binding,
        "risk_multiplier": mult,
        "constraints": {
            "C1_policy_cap_20pct_turnover": c1,
            "C2_working_capital_need": c2,
            "C3_repayment_capacity": c3,
            "C4_risk_appetite_adjusted": c4,
            "C5_exposure_headroom": c5,
        },
        "note": note,
    }
