"""
The "reconciliation" half of the triangulation engine: turns Layer 2's trust
weights into a single confidence-weighted effective turnover figure, then
derives working capital gap, repayment capacity, and a current DSCR from it
plus the other Layer 1 inputs the diagram lists (EBITDA, debtor/creditor
days, debt obligations).

Two named, defensible methods are used instead of an opaque guess:

1. Working capital gap - Nayak Committee turnover method: WC requirement =
   25% of annual turnover, of which banks conventionally fund 20% (5% is
   promoter margin). This is the standard simplified method Indian banks use
   for SME working-capital limits up to ~Rs 5 crore, and it only needs a
   turnover figure (which we have), unlike the Tandon/MPBF method which
   needs a full current-asset/liability breakup we don't extract yet.
2. Operating-cycle cross-check - funds locked in the receivables/payables
   cycle: (debtor_days/365)*turnover - (creditor_days/365)*purchases. We
   report the lower (more conservative) of the two when both are available.

Repayment capacity assumes existing bureau exposure is serviced at
ASSUMED_ANNUAL_DEBT_SERVICE_RATE - a simplifying stand-in for not having
itemized loan tenor/rate yet (flagged honestly, not hidden).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

ASSUMED_ANNUAL_DEBT_SERVICE_RATE = 0.30  # existing exposure serviced over ~3.3 yrs blended P&I


def _weighted_average(values: Dict[str, float], weights: Dict[str, float]) -> Optional[float]:
    usable = {k: v for k, v in values.items() if v is not None and k in weights}
    if not usable:
        return None
    total_weight = sum(weights[k] for k in usable)
    if total_weight <= 0:
        return sum(usable.values()) / len(usable)  # plain average fallback
    return sum(usable[k] * weights[k] for k in usable) / total_weight


def compute_effective_metrics(
    source_jsons: Dict[str, Any],
    aggregated_weights: Dict[str, float],
    pairwise: Dict[str, Any],
) -> Dict[str, Any]:
    gst = (source_jsons.get("gst") or {}).get("data")
    banking = (source_jsons.get("banking") or {}).get("data")
    financials = (source_jsons.get("financials") or {}).get("data")
    ledger = (source_jsons.get("ledger") or {}).get("data")
    bureau = (source_jsons.get("bureau") or {}).get("data")

    notes: list[str] = []

    turnover_values = {
        "gst": gst.get("gstr3b_annual_turnover") if gst else None,
        "bank": banking.get("inferred_annual_turnover") if banking else None,
        "financials": financials.get("revenue") if financials else None,
        "ledger": ledger.get("total_sales") if ledger else None,
    }
    available = {k: v for k, v in turnover_values.items() if v is not None}

    if len(available) >= 2:
        effective_turnover = _weighted_average(turnover_values, aggregated_weights)
        confidence = round(sum(p["trust_weight"] for p in pairwise.values()) / len(pairwise), 3) if pairwise else 0.5
    elif len(available) == 1:
        effective_turnover = next(iter(available.values()))
        confidence = 0.35
        notes.append("Only one turnover source available - effective_turnover is unverified, confidence capped low.")
    else:
        effective_turnover = None
        confidence = 0.0
        notes.append("No turnover sources available at all.")

    # --- Working capital gap ---
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
            notes.append("Could not compute working_capital_gap - missing effective_turnover and/or ledger data.")

    # --- Repayment capacity & DSCR ---
    ebitda = financials.get("ebitda") if financials else None
    existing_exposure = bureau.get("total_exposure") if bureau else 0
    annual_debt_service_existing = round(existing_exposure * ASSUMED_ANNUAL_DEBT_SERVICE_RATE) if existing_exposure else 0

    if ebitda is None:
        repayment_capacity = None
        current_dscr = None
        notes.append("No financials data - cannot compute repayment_capacity or current_dscr.")
    else:
        repayment_capacity = round(max(0.0, ebitda - annual_debt_service_existing))
        current_dscr = round(ebitda / annual_debt_service_existing, 2) if annual_debt_service_existing > 0 else None

    return {
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
    }
