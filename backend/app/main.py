from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.graphdb.schema import ensure_constraints
from app.routers import layer1, layer2, layer3, layer4, layer5, layer6

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
