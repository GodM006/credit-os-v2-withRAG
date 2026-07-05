"""
Inference wrapper for the Layer 5 risk model.

Returns:
  pd          Probability of Default (0.0 - 1.0)
  risk_score  83-point Amex-style score (inverse of PD, 1 = highest risk,
              83 = lowest risk — matching the Amex leaderboard convention).
              Formula: round((1 - pd) * 82) + 1, so PD=0 → 83, PD=1 → 1.
  lgd         Loss Given Default estimate. We use a simplified LGD based on
              the collateral proxy (net_worth vs total_exposure). In SME
              lending without hard collateral this is almost always 0.65-0.85;
              we compute it rather than hard-code it so it responds to the
              applicant's actual financials.
  risk_band   Standard 5-band label derived from risk_score.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import numpy as np

from app.ml.features import FEATURE_NAMES, features_as_vector
from app.ml.trainer import load_model

logger = logging.getLogger(__name__)

_model_cache: Optional[dict] = None

RISK_BANDS = [
    (75, 83, "A — Very Low Risk"),
    (60, 74, "B — Low Risk"),
    (40, 59, "C — Medium Risk"),
    (20, 39, "D — High Risk"),
    (1,  19, "E — Very High Risk"),
]


def _get_model() -> dict:
    global _model_cache
    if _model_cache is None:
        _model_cache = load_model()
    return _model_cache


def _risk_band(score: int) -> str:
    for lo, hi, label in RISK_BANDS:
        if lo <= score <= hi:
            return label
    return "E — Very High Risk"


def _estimate_lgd(effective_metrics: Dict[str, Any], source_jsons: Dict[str, Any]) -> float:
    """
    Simplified LGD:  LGD = 1 - recovery_rate
    Recovery rate is estimated from net_worth / total_exposure (asset coverage).
    Capped at 0.35 (max 35% recovery assumed in unsecured SME lending) and
    floored at 0.0 (no negative loss given default).
    Baseline LGD of 0.75 when we can't compute a ratio.
    """
    financials = (source_jsons.get("financials") or {}).get("data") or {}
    bureau = (source_jsons.get("bureau") or {}).get("data") or {}
    net_worth = financials.get("net_worth")
    total_exposure = bureau.get("total_exposure")

    if net_worth is None or total_exposure is None or total_exposure <= 0:
        return 0.75

    asset_coverage = max(0.0, net_worth / total_exposure)
    recovery_rate = min(0.35, asset_coverage * 0.25)
    return round(1.0 - recovery_rate, 3)


def run_inference(state: Dict[str, Any]) -> Dict[str, Any]:
    model_bundle = _get_model()
    pipeline = model_bundle["pipeline"]

    vec = features_as_vector(state)
    X = np.array(vec, dtype=np.float32).reshape(1, -1)

    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
        pd_val = float(pipeline.predict_proba(X)[0, 1])
    risk_score = max(1, min(83, round((1 - pd_val) * 82) + 1))
    lgd = _estimate_lgd(state.get("effective_metrics", {}), state.get("source_jsons", {}))
    expected_loss_rate = round(pd_val * lgd, 4)

    return {
        "pd": round(pd_val, 4),
        "risk_score": risk_score,
        "risk_band": _risk_band(risk_score),
        "lgd": lgd,
        "expected_loss_rate": expected_loss_rate,
        "model_name": model_bundle.get("model_name", "unknown"),
        "trained_on": "synthetic" if model_bundle.get("n_rows") else "unknown",
    }
