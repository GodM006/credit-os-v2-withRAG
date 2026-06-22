"""
Trains the placeholder ML risk model on synthetic data with the same feature
schema as the Amex default prediction dataset.

Model choice: LightGBM (lgbm) if available, else LogisticRegression.
The diagram mentions XGBoost and LightGBM; we pick LightGBM first because
its native handling of class imbalance (is_unbalance=True) is better for
credit default prediction without needing to tune sample_weight manually.

Synthetic label generation: a deterministic-ish rule that maps the "risky"
features onto a higher default probability, so the model learns something
meaningful even before the real Amex CSV is plugged in. Specifically:
  - bureau_score < 650 -> higher PD
  - written_off_accounts > 0 -> high PD
  - dpd_90_plus_count > 0 -> high PD
  - dscr < 1.0 -> higher PD
  - fraud_risk_encoded == 2 -> high PD
  - cash_deposit_ratio > 0.35 -> slightly higher PD

This means the model will behave sensibly (reject fraud_risk=high, approve
clean profiles) without any real labelled data, and smoothly improve when
real data replaces this generator.
"""
from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import Tuple

import numpy as np

logger = logging.getLogger(__name__)

MODEL_PATH = Path(__file__).parent / "risk_model.joblib"
N_SYNTHETIC_ROWS = 4_000
RANDOM_SEED = 42


def _synthetic_row(rng: random.Random) -> Tuple[list, int]:
    """Returns (feature_vector, label) where label=1 means default."""
    bureau_score = rng.randint(480, 880)
    dpd_90 = rng.choices([0, 1, 2], weights=[80, 13, 7])[0]
    written_off = rng.choices([0, 1], weights=[90, 10])[0]
    dscr = round(rng.uniform(0.5, 3.5), 2)
    debt_equity = round(rng.uniform(0.1, 5.0), 2)
    fraud_risk = rng.choices([0, 1, 2], weights=[60, 30, 10])[0]
    cash_dep_ratio = round(rng.uniform(0.01, 0.55), 2)
    bounce_count = rng.randint(0, 8)
    gst_vintage = rng.randint(6, 120)
    anchor_conc = round(rng.uniform(10, 90), 1)
    dpd_30 = rng.choices([0, 1, 2], weights=[70, 20, 10])[0]
    dpd_60 = rng.choices([0, 1], weights=[85, 15])[0]
    overdue = rng.uniform(0, 500_000) if dpd_30 > 0 else 0
    enquiries = rng.randint(0, 10)
    effective_turnover = rng.uniform(1_000_000, 50_000_000)
    confidence = round(rng.uniform(0.2, 0.98), 2)
    net_worth = rng.uniform(-500_000, 10_000_000)
    total_exposure = round(effective_turnover * rng.uniform(0.05, 0.35))

    # Synthetic PD signal
    pd_score = 0.05
    pd_score += max(0, (650 - bureau_score) / 650) * 0.30
    pd_score += dpd_90 * 0.15
    pd_score += written_off * 0.25
    pd_score += max(0, (1.0 - dscr) / 1.0) * 0.15
    pd_score += fraud_risk * 0.10
    pd_score += max(0, cash_dep_ratio - 0.30) * 0.20
    pd_score += max(0, (anchor_conc - 65) / 35) * 0.05
    pd_score = min(pd_score, 0.97)
    label = 1 if rng.random() < pd_score else 0

    features = [
        bureau_score, dpd_30, dpd_60, dpd_90, total_exposure, overdue,
        written_off, enquiries, dscr, debt_equity, effective_turnover,
        confidence, cash_dep_ratio, bounce_count, gst_vintage, anchor_conc,
        net_worth, fraud_risk,
    ] + [0.0] * 170  # amex fillers

    return features, label


def generate_synthetic_dataset() -> Tuple[np.ndarray, np.ndarray]:
    rng = random.Random(RANDOM_SEED)
    X, y = [], []
    for _ in range(N_SYNTHETIC_ROWS):
        row, label = _synthetic_row(rng)
        X.append(row)
        y.append(label)
    return np.array(X, dtype=np.float32), np.array(y, dtype=np.int8)


def train_and_save() -> None:
    import joblib
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    logger.info("Generating %d synthetic training rows…", N_SYNTHETIC_ROWS)
    X, y = generate_synthetic_dataset()
    logger.info("Default rate in synthetic data: %.1f%%", 100 * y.mean())

    try:
        from lightgbm import LGBMClassifier
        clf = LGBMClassifier(
            n_estimators=200,
            learning_rate=0.05,
            max_depth=6,
            is_unbalance=True,
            random_state=RANDOM_SEED,
            verbose=-1,
        )
        model_name = "LightGBM"
    except ImportError:
        from sklearn.linear_model import LogisticRegression
        clf = LogisticRegression(max_iter=500, class_weight="balanced", random_state=RANDOM_SEED)
        model_name = "LogisticRegression"

    pipe = Pipeline([("scaler", StandardScaler()), ("clf", clf)])
    pipe.fit(X, y)

    joblib.dump({"pipeline": pipe, "model_name": model_name, "n_rows": N_SYNTHETIC_ROWS}, MODEL_PATH)
    logger.info("Saved %s model to %s", model_name, MODEL_PATH)


def load_model():
    import joblib
    if not MODEL_PATH.exists():
        logger.info("No model found at %s - training now on synthetic data…", MODEL_PATH)
        train_and_save()
    return joblib.load(MODEL_PATH)
