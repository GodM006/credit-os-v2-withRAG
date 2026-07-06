"""
Reconciliation half of the triangulation engine — Layer 3.

Upgrades from the original weighted-mean design:

  Layer C (Robust Centre):
    Replaces _weighted_average() with a weighted-median / MAD approach.
    With only 4 data points, a plain weighted mean is easily pulled hard by
    one bad outlier.  The weighted median is the standard robust-statistics
    alternative.  Each source's distance from the median is converted to a
    smooth deviation-trust multiplier via a logistic (Cauchy-like) function
    instead of the four hardcoded piecewise breakpoints in trust_weights.py.

  Layer D (Composite Confidence):
    Replaces confidence = sum(pairwise_trust)/len(pairwise) with a three-
    factor product:
        confidence = corroboration_factor × agreement_factor × evidence_factor
    Each factor is independently inspectable in triangulation_detail, so a
    low confidence score has a traceable cause (too few sources? too spread?
    bad extractions?).

Both layers consume the evidence_prior values computed by evidence_priors.py
(Layer A) so extraction quality discounts propagate into the final weights.

The output dict preserves every existing key that Layer 4/5/6 consume
(effective_turnover, confidence, working_capital_gap, repayment_capacity,
current_dscr, annual_debt_service_existing, notes).  The new
triangulation_detail key is purely additive.

Working-capital and repayment capacity logic is unchanged from the original.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

ASSUMED_ANNUAL_DEBT_SERVICE_RATE = 0.30  # existing exposure serviced over ~3.3 yrs blended P&I

# Scale factor for the logistic deviation-trust curve.
# Higher = more tolerant of spread between sources (wider trust band).
# 1.5 is a reasonable default for SME financial document quality.
_DEVIATION_SCALE = 1.5


# ---------------------------------------------------------------------------
# Layer C helpers — weighted median + MAD
# ---------------------------------------------------------------------------

def _weighted_median(values: List[float], weights: List[float]) -> Optional[float]:
    """
    Compute the weighted median.
    Returns None if the inputs are empty or total weight is zero.

    Algorithm: sort by value, accumulate weights, return the value at the
    50th weight-percentile (standard interpolated weighted median).
    """
    paired = [(v, w) for v, w in zip(values, weights) if w > 0]
    if not paired:
        return None
    paired.sort(key=lambda x: x[0])
    total_weight = sum(w for _, w in paired)
    if total_weight <= 0:
        return None
    target = total_weight / 2.0
    cumulative = 0.0
    for value, weight in paired:
        cumulative += weight
        if cumulative >= target:
            return value
    return paired[-1][0]


def _mad(values: List[float], center: float) -> float:
    """Median Absolute Deviation from a given center."""
    deviations = [abs(v - center) for v in values]
    deviations.sort()
    n = len(deviations)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2 == 0:
        return (deviations[mid - 1] + deviations[mid]) / 2.0
    return deviations[mid]


def _deviation_trust(deviation: float, mad: float) -> float:
    """
    Smooth logistic (Cauchy-like) mapping from deviation → trust multiplier.

    deviation_trust = 1 / (1 + (deviation / (mad × scale))²)

    At deviation = 0            → trust = 1.0
    At deviation = mad × scale  → trust = 0.5
    At deviation >> mad         → trust → 0.0

    Replaces the 4 arbitrary piecewise breakpoints in trust_weights.py with
    one continuous, principled function.
    """
    if mad <= 0:
        # All values are identical — full trust for every source
        return 1.0
    ratio = deviation / (mad * _DEVIATION_SCALE)
    return 1.0 / (1.0 + ratio ** 2)


# ---------------------------------------------------------------------------
# Layer C — robust centre (replaces _weighted_average)
# ---------------------------------------------------------------------------

def _robust_centre(
    turnover_values: Dict[str, Optional[float]],
    evidence_priors: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Compute the evidence-and-deviation-weighted centre of the turnover
    estimates, using the weighted median as the robust centre.

    Returns:
        {
            "effective_turnover": float | None,
            "robust_center": float | None,
            "mad": float | None,
            "per_source": {source: {"raw_value", "evidence_prior",
                                    "deviation_trust", "final_weight",
                                    "excluded"}},
            "excluded_sources": [...],
        }
    """
    # Only include sources that have a value AND are not excluded by evidence_priors
    ep = evidence_priors.get("per_source", {})
    excluded_from_prior = set(evidence_priors.get("excluded_sources", []))

    usable: Dict[str, float] = {}
    for source, raw_val in turnover_values.items():
        if raw_val is None:
            continue
        if source in excluded_from_prior:
            continue
        prior = ep.get(source, {}).get("evidence_prior", 0.5)
        if prior <= 0:
            continue
        usable[source] = raw_val

    per_source_detail: Dict[str, Any] = {}

    # Build full per_source_detail for ALL sources (including excluded/missing)
    for source, raw_val in turnover_values.items():
        ep_entry = ep.get(source, {})
        per_source_detail[source] = {
            "raw_value": raw_val,
            "evidence_prior": ep_entry.get("evidence_prior"),
            "deviation_trust": None,
            "final_weight": None,
            "excluded": ep_entry.get("excluded", raw_val is None),
        }

    if not usable:
        return {
            "effective_turnover": None,
            "robust_center": None,
            "mad": None,
            "per_source": per_source_detail,
            "excluded_sources": list(excluded_from_prior | {s for s, v in turnover_values.items() if v is None}),
        }

    values_list = list(usable.values())
    sources_list = list(usable.keys())
    # Initial weights = evidence_prior (before deviation penalty)
    prior_weights = [ep.get(s, {}).get("evidence_prior", 0.5) for s in sources_list]

    # Step 1: weighted median using evidence priors as initial weights
    robust_center = _weighted_median(values_list, prior_weights)
    if robust_center is None:
        robust_center = sum(values_list) / len(values_list)

    # Step 2: MAD
    mad_val = _mad(values_list, robust_center)

    # Step 3: deviation trust for each usable source
    deviation_trusts = [_deviation_trust(abs(v - robust_center), mad_val) for v in values_list]

    # Step 4: final weight = evidence_prior × deviation_trust
    final_weights = [p * d for p, d in zip(prior_weights, deviation_trusts)]

    # Step 5: evidence-weighted value (close to weighted median)
    total_final_weight = sum(final_weights)
    if total_final_weight > 0:
        effective_turnover = sum(v * w for v, w in zip(values_list, final_weights)) / total_final_weight
    else:
        effective_turnover = robust_center

    # Update per_source_detail with computed values
    for i, source in enumerate(sources_list):
        per_source_detail[source].update({
            "deviation_trust": round(deviation_trusts[i], 4),
            "final_weight": round(final_weights[i], 4),
        })

    excluded_all = list(
        excluded_from_prior
        | {s for s, v in turnover_values.items() if v is None and s not in usable}
    )

    return {
        "effective_turnover": effective_turnover,
        "robust_center": round(robust_center, 2),
        "mad": round(mad_val, 2),
        "per_source": per_source_detail,
        "excluded_sources": excluded_all,
    }


# ---------------------------------------------------------------------------
# Layer D — composite confidence
# ---------------------------------------------------------------------------

def _composite_confidence(
    per_source_detail: Dict[str, Any],
    robust_center: Optional[float],
    mad: Optional[float],
    total_sources: int = 4,
) -> Dict[str, Any]:
    """
    Three-factor composite confidence score:
        confidence = corroboration_factor × agreement_factor × evidence_factor

    corroboration_factor  — how many sources contributed
    agreement_factor      — how tightly they agree (MAD-based)
    evidence_factor       — mean evidence_prior of usable sources
    """
    usable = [v for v in per_source_detail.values() if not v.get("excluded") and v.get("raw_value") is not None]
    usable_count = len(usable)

    corroboration_factor = usable_count / max(total_sources, 1)

    if robust_center and robust_center > 0 and mad is not None:
        # Normalised MAD coefficient of variation; clamp to [0, 1]
        cv = min(mad / robust_center, 1.0)
        agreement_factor = 1.0 / (1.0 + cv)
    else:
        agreement_factor = 0.5 if usable_count >= 1 else 0.0

    if usable_count > 0:
        evidence_factor = sum(
            v.get("evidence_prior") or 0.0
            for v in usable
        ) / usable_count
    else:
        evidence_factor = 0.0

    confidence = corroboration_factor * agreement_factor * evidence_factor
    confidence = round(min(1.0, max(0.0, confidence)), 3)

    return {
        "confidence": confidence,
        "corroboration_factor": round(corroboration_factor, 3),
        "agreement_factor": round(agreement_factor, 3),
        "evidence_factor": round(evidence_factor, 3),
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def compute_effective_metrics(
    source_jsons: Dict[str, Any],
    aggregated_weights: Dict[str, float],    # kept for API compat; now informational only
    pairwise: Dict[str, Any],                # kept for API compat
    evidence_priors: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Compute reconciled effective turnover and derived credit metrics.

    evidence_priors: output of evidence_priors.compute_evidence_priors().
    If not provided (backward compat), a neutral-prior stub is used so
    existing callers without evidence_priors still work.
    """
    gst = (source_jsons.get("gst") or {}).get("data")
    banking = (source_jsons.get("banking") or {}).get("data")
    financials = (source_jsons.get("financials") or {}).get("data")
    ledger = (source_jsons.get("ledger") or {}).get("data")
    bureau = (source_jsons.get("bureau") or {}).get("data")

    notes: list[str] = []

    # Fallback neutral priors if not provided
    if evidence_priors is None:
        evidence_priors = {
            "per_source": {s: {"evidence_prior": 0.5, "excluded": False, "reason": None} for s in ("gst", "bank", "financials", "ledger")},
            "excluded_sources": [],
            "intra_source_flags": [],
            "gst_self_inconsistency_pct": None,
        }

    turnover_values: Dict[str, Optional[float]] = {
        "gst": gst.get("gstr3b_annual_turnover") if gst else None,
        "bank": banking.get("inferred_annual_turnover") if banking else None,
        "financials": financials.get("revenue") if financials else None,
        "ledger": ledger.get("total_sales") if ledger else None,
    }

    # -----------------------------------------------------------------------
    # Layer C — Robust centre
    # -----------------------------------------------------------------------
    centre_result = _robust_centre(turnover_values, evidence_priors)
    effective_turnover = centre_result["effective_turnover"]
    robust_center = centre_result["robust_center"]
    mad_val = centre_result["mad"]
    per_source_detail = centre_result["per_source"]

    available_count = sum(1 for v in turnover_values.values() if v is not None)
    usable_count = sum(1 for s in per_source_detail.values() if not s.get("excluded") and s.get("raw_value") is not None)

    if usable_count == 0 and available_count == 1:
        # Single unexcluded source
        effective_turnover = next((v for v in turnover_values.values() if v is not None), None)
        notes.append("Only one turnover source available — effective_turnover is unverified, confidence capped low.")
    elif usable_count == 0:
        notes.append("No usable turnover sources — all sources missing or excluded as invalid.")

    # -----------------------------------------------------------------------
    # Layer D — Composite confidence
    # -----------------------------------------------------------------------
    conf_result = _composite_confidence(per_source_detail, robust_center, mad_val)
    confidence = conf_result["confidence"]

    # Cap at 0.35 when only one source survives
    if usable_count <= 1:
        confidence = min(confidence, 0.35)

    # -----------------------------------------------------------------------
    # triangulation_detail (additive — no existing key removed)
    # -----------------------------------------------------------------------
    triangulation_detail: Dict[str, Any] = {
        "method": "evidence_weighted_median",
        "robust_center": robust_center,
        "mad": mad_val,
        "per_source": per_source_detail,
        "excluded_sources": centre_result["excluded_sources"],
        "intra_source_flags": evidence_priors.get("intra_source_flags", []),
        "gst_self_inconsistency_pct": evidence_priors.get("gst_self_inconsistency_pct"),
        "confidence_breakdown": {
            "corroboration_factor": conf_result["corroboration_factor"],
            "agreement_factor": conf_result["agreement_factor"],
            "evidence_factor": conf_result["evidence_factor"],
        },
    }

    # -----------------------------------------------------------------------
    # Working capital gap (unchanged logic)
    # -----------------------------------------------------------------------
    wc_turnover_method = round(0.20 * effective_turnover) if effective_turnover else None
    wc_operating_cycle = None
    if ledger and effective_turnover:
        debtor_days = ledger.get("debtor_days") or 0.0
        creditor_days = ledger.get("creditor_days") or 0.0
        total_purchases = ledger.get("total_purchases") or 0.0
        wc_operating_cycle = round(
            max(0.0, (debtor_days / 365) * effective_turnover - (creditor_days / 365) * total_purchases)
        )

    if wc_turnover_method is not None and wc_operating_cycle is not None:
        working_capital_gap = min(wc_turnover_method, wc_operating_cycle)
    else:
        working_capital_gap = wc_turnover_method if wc_turnover_method is not None else wc_operating_cycle
        if working_capital_gap is None:
            notes.append("Could not compute working_capital_gap — missing effective_turnover and/or ledger data.")

    # -----------------------------------------------------------------------
    # Repayment capacity & DSCR (unchanged logic)
    # -----------------------------------------------------------------------
    ebitda = financials.get("ebitda") if financials else None
    existing_exposure = bureau.get("total_exposure") if bureau else 0
    annual_debt_service_existing = round(existing_exposure * ASSUMED_ANNUAL_DEBT_SERVICE_RATE) if existing_exposure else 0

    if ebitda is None:
        repayment_capacity = None
        current_dscr = None
        notes.append("No financials data — cannot compute repayment_capacity or current_dscr.")
    else:
        repayment_capacity = round(max(0.0, ebitda - annual_debt_service_existing))
        current_dscr = round(ebitda / annual_debt_service_existing, 2) if annual_debt_service_existing > 0 else None

    return {
        # ---- Existing keys — unchanged for backward compat ----
        "effective_turnover": round(effective_turnover) if effective_turnover else None,
        "confidence": confidence,
        "working_capital_gap": working_capital_gap,
        "working_capital_gap_methods": {
            "turnover_method_20pct": wc_turnover_method,
            "operating_cycle": wc_operating_cycle,
        },
        "repayment_capacity": repayment_capacity,
        "current_dscr": current_dscr,
        "annual_debt_service_existing": annual_debt_service_existing,
        "notes": notes,
        # ---- New additive key ----
        "triangulation_detail": triangulation_detail,
    }
