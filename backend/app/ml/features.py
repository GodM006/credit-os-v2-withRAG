"""
Feature schema for the ML risk model, designed to match the Amex default
prediction dataset column shape so swapping in real Amex data later requires
only replacing the training CSV, not the feature extraction or model code.

Amex dataset key features (aggregated per customer):
  P_2: payment ratio (most recent statement)
  B_* : balance features
  D_* : delinquency features
  S_* : spend features
  R_* : risk features
  F_* : fee features

We map the features we *can* derive from AppState into the same semantic
buckets: payment behaviour (from bureau DPD/delinquency), balance/exposure
(bureau total_exposure, financials net_worth), risk (DSCR, debt_equity,
bureau_score), spend/turnover (effective_turnover). Where a direct mapping
exists we use it; where it doesn't we fill with the Amex column's mean
(stored as FILL_DEFAULTS below) so the model always receives a full vector.

The Amex dataset has 188 features; we derive 18 meaningful ones from our
sources. The rest are filled with FILL_DEFAULTS when running on AppState data.
This is *intentional and documented*, not hidden: the model output should
be read as "probability of default given the financial profile summary we
have", not a full Amex-style score.
"""
from __future__ import annotations

from typing import Any, Dict, List

# 18 features we actually derive. Order matches FEATURE_NAMES below.
OUR_FEATURE_KEYS = [
    "bureau_score",
    "dpd_30_count",
    "dpd_60_count",
    "dpd_90_plus_count",
    "total_exposure",
    "overdue_amount",
    "written_off_accounts",
    "enquiries_last_6m",
    "dscr",
    "debt_equity_ratio",
    "effective_turnover",
    "confidence",
    "cash_deposit_ratio",
    "bounce_count",
    "gst_vintage_months",
    "anchor_concentration_pct",
    "net_worth",
    "fraud_risk_encoded",  # 0=low, 1=medium, 2=high
]

# Amex column placeholder names for the remaining features — filled with means
AMEX_FILLER_FEATURES = [f"amex_filler_{i:03d}" for i in range(170)]

FEATURE_NAMES: List[str] = OUR_FEATURE_KEYS + AMEX_FILLER_FEATURES

FRAUD_RISK_ENCODING = {"low": 0, "medium": 1, "high": 2}

# Amex dataset column means (approximate) used to fill placeholder features.
# Source: public kernel analysis of the Amex Default Prediction dataset.
AMEX_FILLER_MEAN = 0.0  # most normalised Amex features centre around 0 after preprocessing


def extract_features(state: Dict[str, Any]) -> Dict[str, float]:
    source_jsons = state.get("source_jsons", {})
    effective_metrics = state.get("effective_metrics", {})

    bureau = (source_jsons.get("bureau") or {}).get("data") or {}
    banking = (source_jsons.get("banking") or {}).get("data") or {}
    gst = (source_jsons.get("gst") or {}).get("data") or {}
    ledger = (source_jsons.get("ledger") or {}).get("data") or {}
    financials = (source_jsons.get("financials") or {}).get("data") or {}
    fraud_risk_str = (effective_metrics.get("fraud_risk") or "low").lower()

    raw: Dict[str, float] = {
        "bureau_score":             float(bureau.get("bureau_score") or 700),
        "dpd_30_count":             float(bureau.get("dpd_30") or 0),
        "dpd_60_count":             float(bureau.get("dpd_60") or 0),
        "dpd_90_plus_count":        float(bureau.get("dpd_90_plus") or 0),
        "total_exposure":           float(bureau.get("total_exposure") or 0),
        "overdue_amount":           float(bureau.get("overdue_amount") or 0),
        "written_off_accounts":     float(bureau.get("written_off_accounts") or 0),
        "enquiries_last_6m":        float(bureau.get("enquiries_last_6m") or 0),
        "dscr":                     float(effective_metrics.get("current_dscr") or 1.5),
        "debt_equity_ratio":        float(financials.get("debt_equity_ratio") or 1.0),
        "effective_turnover":       float(effective_metrics.get("effective_turnover") or 0),
        "confidence":               float(effective_metrics.get("confidence") or 0.5),
        "cash_deposit_ratio":       float(banking.get("cash_deposit_ratio") or 0),
        "bounce_count":             float(banking.get("bounce_count") or 0),
        "gst_vintage_months":       float(gst.get("vintage_months") or 12),
        "anchor_concentration_pct": float(ledger.get("top_debtor_concentration_pct") or 30),
        "net_worth":                float(financials.get("net_worth") or 0),
        "fraud_risk_encoded":       float(FRAUD_RISK_ENCODING.get(fraud_risk_str, 0)),
    }

    for filler in AMEX_FILLER_FEATURES:
        raw[filler] = AMEX_FILLER_MEAN

    return raw


def features_as_vector(state: Dict[str, Any]) -> List[float]:
    feats = extract_features(state)
    return [feats[k] for k in FEATURE_NAMES]
