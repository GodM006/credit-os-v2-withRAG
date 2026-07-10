from __future__ import annotations

# app.config sets OMP_NUM_THREADS=1 as a side effect of import; keep it first.
from app.config import settings


def _warm_layer5_model() -> None:
    """Run one dummy Layer 5 inference NOW, before any other heavy import.

    This is load-bearing for macOS and must stay at the very top of this module,
    before the routers are imported. Two things depend on it:

      1. LightGBM's OpenMP (libomp) runtime must initialize BEFORE the Layer 1
         RAG stack (PyTorch / sentence-transformers / chromadb+onnxruntime),
         which each bundle their own OpenMP. When a second, different OpenMP
         runtime loads into the process it aborts with a duplicate-runtime
         segfault — crashing the whole backend the first time Layer 5 runs.
         Initializing LightGBM first makes the others coexist. A bare model
         load is NOT enough; only an actual predict initializes the runtime.
      2. It also removes the ~0.7s cold-load latency from the first request.

    It must run at import time on the main thread (not in a startup event): a
    real predict on uvicorn's asyncio startup thread deadlocks LightGBM's
    OpenMP thread pool. OMP_NUM_THREADS=1 (set in app.config) is also required.
    """
    try:
        from app.ml.inference import run_inference

        run_inference({})
    except Exception as exc:  # never block startup if the model is unavailable
        import logging

        logging.getLogger(__name__).warning("Layer 5 model warmup skipped: %s", exc)


_warm_layer5_model()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.graphdb.schema import ensure_constraints
from app.routers import admin, layer1, layer2, layer3, layer4, layer5, layer6

app = FastAPI(
    title="Credit Decisioning OS",
    description="Agentic credit underwriting backend. Layers 1-6.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(layer1.router)
app.include_router(layer2.router)
app.include_router(layer3.router)
app.include_router(layer4.router)
app.include_router(layer5.router)
app.include_router(layer6.router)
app.include_router(admin.router)


@app.on_event("startup")
def on_startup():
    ensure_constraints()


@app.get("/")
def root():
    return {
        "status": "ok",
        "service": "credit-decisioning-os",
        "version": "1.0.0",
        "layers_implemented": [1, 2, 3, 4, 5, 6],
    }


@app.get("/health")
def health():
    return {"status": "ok"}
