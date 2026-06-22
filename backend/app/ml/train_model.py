"""
Run this once after pip install to pre-train and cache the placeholder model:

    python -m app.ml.train_model

If you don't run it, the model trains automatically on the first
/api/layer5 request (adds ~5-10 seconds to that call). After training the
.joblib file is reused on every subsequent run.

To retrain from scratch (e.g. after swapping in real Amex data):
    python -m app.ml.train_model --retrain
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the Credit OS ML risk model.")
    parser.add_argument("--retrain", action="store_true", help="Delete existing model and retrain from scratch.")
    args = parser.parse_args()

    from app.ml.trainer import MODEL_PATH, train_and_save

    if args.retrain and MODEL_PATH.exists():
        MODEL_PATH.unlink()
        logging.info("Deleted existing model at %s", MODEL_PATH)

    if MODEL_PATH.exists():
        logging.info("Model already exists at %s. Use --retrain to replace it.", MODEL_PATH)
        sys.exit(0)

    train_and_save()
    logging.info("Done. Model saved to %s", MODEL_PATH)


if __name__ == "__main__":
    main()
