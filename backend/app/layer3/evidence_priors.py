"""
Layer A — Evidence Quality Prior
Layer B — Intra-source Self-Consistency Check

Layer A computes a per-source prior trust score BEFORE any cross-source
comparison takes place.  It uses data that already exists in every
ExtractionResult envelope written by Layer 1:

    source_jsons[source]["confidence"]         float 0-1
    source_jsons[source]["validation_status"]  "valid" / "valid_with_warnings" / "invalid"
    source_jsons["financials"]["data"]["is_audited"]  bool (financials only)

Prior formula:
    evidence_prior = base_confidence × validation_penalty × audit_bonus

    validation_penalty:
        "valid"                → 1.00
        "valid_with_warnings"  → 0.75   (LLM itself flagged something; reduce trust)
        "invalid"              → 0.00   (source excluded from reconciliation entirely)

    audit_bonus (financials only):
        is_audited = True      → 1.00  (no extra bonus beyond clean confidence)
        is_audited = False     → 0.85  (unaudited accounts are inherently less reliable)
        missing field          → 1.00  (unknown → don't penalise)

Layer B checks GSTR-3B vs GSTR-1 self-consistency for the GST source.
If `abs(gstr3b - gstr1) / max(gstr3b, gstr1, 1) > GST_SELF_CONSISTENCY_THRESHOLD`:
  - An additional multiplier of 0.85 is applied to the GST evidence_prior
    (a source that disagrees with itself is a weaker cross-source comparator).
  - A flag "gst_self_inconsistent" is added to `intra_source_flags` so
    fraud_signals.py can emit a formal fraud signal without duplicating the math.

Public API
----------
compute_evidence_priors(source_jsons) → EvidencePriorResult
    Returns a typed dict with per-source priors, exclusion flags, and
    intra-source flags. Consumed by trust_aggregation.py and effective_metrics.py.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# --------------------------------------------------------------------------
# Constants (tune these in config.py if you want env-variable control)
# --------------------------------------------------------------------------

VALIDATION_PENALTIES: Dict[str, float] = {
    "valid": 1.00,
    "valid_with_warnings": 0.75,
    "invalid": 0.00,
}

AUDIT_PENALTY_UNAUDITED = 0.85   # multiplier when financials.is_audited is False
GST_SELF_CONSISTENCY_THRESHOLD = 0.10   # 10% divergence between GSTR-3B and GSTR-1
GST_SELF_INCONSISTENCY_DISCOUNT = 0.85  # additional discount on GST prior if self-inconsistent

TURNOVER_SOURCES = ("gst", "bank", "financials", "ledger")

# --------------------------------------------------------------------------
# Internal helpers
# --------------------------------------------------------------------------

def _get_envelope(source_jsons: Dict[str, Any], source: str) -> Optional[Dict[str, Any]]:
    """Return the raw ExtractionResult envelope dict for a source, or None."""
    return source_jsons.get(source) or None


def _evidence_prior_single(
    source: str,
    envelope: Optional[Dict[str, Any]],
    source_jsons: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Compute evidence_prior for one source.
    Returns a dict with keys: evidence_prior, excluded, reason, base_confidence,
    validation_penalty, audit_bonus.
    """
    if envelope is None:
        return {
            "evidence_prior": 0.0,
            "excluded": True,
            "reason": f"{source}: no extraction result present",
            "base_confidence": None,
            "validation_penalty": None,
            "audit_bonus": None,
        }

    base_confidence: float = float(envelope.get("confidence", 0.5))
    validation_status: str = envelope.get("validation_status", "valid")
    penalty: float = VALIDATION_PENALTIES.get(validation_status, 1.0)

    if penalty == 0.0:
        return {
            "evidence_prior": 0.0,
            "excluded": True,
            "reason": f"{source}: validation_status is 'invalid' — excluded from reconciliation",
            "base_confidence": base_confidence,
            "validation_penalty": 0.0,
            "audit_bonus": None,
        }

    # Audit bonus applies only to financials
    audit_bonus: float = 1.0
    if source == "financials":
        data = (envelope.get("data") or {})
        is_audited = data.get("is_audited")
        if is_audited is False:
            audit_bonus = AUDIT_PENALTY_UNAUDITED

    prior = base_confidence * penalty * audit_bonus
    # Cap at 1.0 in case of floating-point overshoot
    prior = min(1.0, round(prior, 4))

    return {
        "evidence_prior": prior,
        "excluded": False,
        "reason": None,
        "base_confidence": round(base_confidence, 4),
        "validation_penalty": penalty,
        "audit_bonus": round(audit_bonus, 4),
    }


# --------------------------------------------------------------------------
# Layer B — GST intra-source self-consistency
# --------------------------------------------------------------------------

def _check_gst_self_consistency(
    source_jsons: Dict[str, Any],
) -> tuple[bool, Optional[float]]:
    """
    Return (is_inconsistent, divergence_pct).
    is_inconsistent is True if GSTR-3B and GSTR-1 turnovers diverge by more
    than GST_SELF_CONSISTENCY_THRESHOLD.
    """
    gst_envelope = source_jsons.get("gst") or {}
    gst_data = gst_envelope.get("data") or {}
    t3b = gst_data.get("gstr3b_annual_turnover")
    t1 = gst_data.get("gstr1_annual_turnover")

    if t3b is None or t1 is None:
        return False, None

    try:
        t3b_f = float(t3b)
        t1_f = float(t1)
    except (TypeError, ValueError):
        return False, None

    denom = max(t3b_f, t1_f, 1.0)
    divergence = abs(t3b_f - t1_f) / denom
    return divergence > GST_SELF_CONSISTENCY_THRESHOLD, round(divergence, 4)


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def compute_evidence_priors(source_jsons: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute Layer A evidence priors and Layer B intra-source flags for all
    turnover-bearing sources.

    Returns:
        {
            "per_source": {
                "gst":        {"evidence_prior": float, "excluded": bool, "reason": str|None, ...},
                "bank":       {...},
                "financials": {...},
                "ledger":     {...},
            },
            "excluded_sources": [str, ...],
            "intra_source_flags": [str, ...],
            "gst_self_inconsistency_pct": float | None,
        }
    """
    per_source: Dict[str, Any] = {}
    intra_source_flags: List[str] = []
    gst_inconsistency_pct: Optional[float] = None

    for source in TURNOVER_SOURCES:
        envelope = _get_envelope(source_jsons, source)
        result = _evidence_prior_single(source, envelope, source_jsons)
        per_source[source] = result

    # Layer B — GST self-consistency
    gst_inconsistent, div_pct = _check_gst_self_consistency(source_jsons)
    gst_inconsistency_pct = div_pct

    if gst_inconsistent and not per_source["gst"]["excluded"]:
        # Apply additional discount to GST evidence_prior
        old_prior = per_source["gst"]["evidence_prior"]
        new_prior = round(old_prior * GST_SELF_INCONSISTENCY_DISCOUNT, 4)
        per_source["gst"]["evidence_prior"] = new_prior
        per_source["gst"]["gst_self_inconsistency_discount_applied"] = True
        intra_source_flags.append("gst_self_inconsistent")

    excluded_sources = [s for s, v in per_source.items() if v["excluded"]]

    return {
        "per_source": per_source,
        "excluded_sources": excluded_sources,
        "intra_source_flags": intra_source_flags,
        "gst_self_inconsistency_pct": gst_inconsistency_pct,
    }
