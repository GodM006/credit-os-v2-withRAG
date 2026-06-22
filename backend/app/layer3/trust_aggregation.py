"""
Per the diagram's Layer 3 output example: trust_weights: {gst:0.9, bank:0.88}.
Layer 2 gives us *pairwise* trust weights (gst_vs_bank, bank_vs_financials,
gst_vs_ledger). This aggregates those into one weight per turnover-bearing
source - the average trust weight across every pair that source appears in.

Bureau and KYC aren't included here: they don't make a turnover claim to be
triangulated against the others, so "trust weight" isn't a meaningful concept
for them in this scheme. They still feed into fraud signals and effective
metrics directly (see fraud_signals.py / effective_metrics.py).
"""
from __future__ import annotations

from typing import Any, Dict

# Which sources participate in which Layer 2 pairwise comparison.
PAIR_SOURCES = {
    "gst_vs_bank": ("gst", "bank"),
    "bank_vs_financials": ("bank", "financials"),
    "gst_vs_ledger": ("gst", "ledger"),
}

DEFAULT_TRUST_WEIGHT = 0.5  # neutral fallback when a source has no comparisons at all


def aggregate_source_trust_weights(pairwise: Dict[str, Any]) -> Dict[str, Any]:
    contributions: Dict[str, list] = {"gst": [], "bank": [], "financials": [], "ledger": []}

    for pair_key, sources in PAIR_SOURCES.items():
        pair = pairwise.get(pair_key)
        if not pair:
            continue
        for source in sources:
            contributions[source].append(pair["trust_weight"])

    aggregated = {}
    notes = []
    for source, weights in contributions.items():
        if weights:
            aggregated[source] = round(sum(weights) / len(weights), 3)
        else:
            aggregated[source] = DEFAULT_TRUST_WEIGHT
            notes.append(f"{source}: no pairwise comparisons available, defaulted to {DEFAULT_TRUST_WEIGHT}")

    return {"weights": aggregated, "notes": notes}
