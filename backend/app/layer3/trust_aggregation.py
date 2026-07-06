"""
Per-source trust weight aggregation — repurposed for EWRT.

Previously: averaged pairwise trust weights from Layer 2 per source.
Now: combines Layer 2 pairwise weights with Layer A evidence priors to
produce a final_weight per source, which is what triangulation_detail
surfaces for auditability.

The `aggregated_weights` dict output (keyed by source name, values 0-1)
is preserved for API compatibility with any code that reads it downstream.
The values are now the evidence-prior-discounted weights rather than bare
pairwise averages, which is strictly more informative.
"""
from __future__ import annotations

from typing import Any, Dict

from app.layer3.evidence_priors import compute_evidence_priors

# Which sources participate in which Layer 2 pairwise comparison.
PAIR_SOURCES = {
    "gst_vs_bank": ("gst", "bank"),
    "bank_vs_financials": ("bank", "financials"),
    "gst_vs_ledger": ("gst", "ledger"),
}

DEFAULT_PAIRWISE_WEIGHT = 0.5  # neutral fallback when a source has no pairwise comparisons


def aggregate_source_trust_weights(
    pairwise: Dict[str, Any],
    source_jsons: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Aggregate per-source trust weights combining:
      1. Layer 2 pairwise cross-source agreement weights
      2. Layer A evidence quality priors (confidence × validation_penalty × audit_bonus)

    Returns:
        {
            "weights": {source: final_weight, ...},   # backward-compat key
            "evidence_priors": <EvidencePriorResult>, # Layer A + B output
            "notes": [...],
        }
    """
    # Step 1: Layer A + B — evidence priors
    ep_result = compute_evidence_priors(source_jsons)
    ep_per_source = ep_result.get("per_source", {})

    # Step 2: pairwise average per source (Layer 2, same as before)
    contributions: Dict[str, list] = {"gst": [], "bank": [], "financials": [], "ledger": []}

    for pair_key, sources in PAIR_SOURCES.items():
        pair = pairwise.get(pair_key)
        if not pair:
            continue
        for source in sources:
            contributions[source].append(pair["trust_weight"])

    notes = []
    aggregated: Dict[str, float] = {}

    for source in ("gst", "bank", "financials", "ledger"):
        ep_entry = ep_per_source.get(source, {})
        evidence_prior: float = ep_entry.get("evidence_prior", 0.5)

        if ep_entry.get("excluded"):
            # Source excluded (invalid extraction) → weight = 0
            aggregated[source] = 0.0
            notes.append(f"{source}: excluded — {ep_entry.get('reason', 'unknown reason')}")
            continue

        pairwise_scores = contributions[source]
        if pairwise_scores:
            pairwise_avg = sum(pairwise_scores) / len(pairwise_scores)
        else:
            pairwise_avg = DEFAULT_PAIRWISE_WEIGHT
            notes.append(f"{source}: no pairwise comparisons available, defaulted to {DEFAULT_PAIRWISE_WEIGHT}")

        # Final weight = evidence prior × pairwise agreement
        final_weight = round(evidence_prior * pairwise_avg, 4)
        aggregated[source] = final_weight

    return {
        "weights": aggregated,
        "evidence_priors": ep_result,
        "notes": notes,
    }
