"""
Central configuration for the Credit Decisioning OS backend.

All values are loaded from environment variables (see .env.example).
Nothing here should be hard-coded with secrets.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Groq (LLM) ---
    GROQ_API_KEY: str = ""
    # Reasoning/extraction model. llama-3.3-70b-versatile is the strongest free-tier
    # text model on Groq as of mid-2026; swap via env if it's deprecated later.
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    # Cheaper/faster model, available as a fallback knob if you hit rate limits.
    GROQ_FALLBACK_MODEL: str = "llama-3.1-8b-instant"
    GROQ_TEMPERATURE: float = 0.0
    GROQ_MAX_RETRIES: int = 2

    # --- Neo4j (Layer 2: Context Graph) ---
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = ""
    NEO4J_DATABASE: str = "neo4j"

    # --- Hybrid RAG (Layer 1 retrieval) ---
    # Set RAG_USE_SEMANTIC=false to force BM25-only mode (e.g. low-RAM machines)
    RAG_USE_SEMANTIC: bool = True
    RAG_EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    RAG_BM25_WEIGHT: float = 0.4
    RAG_DENSE_WEIGHT: float = 0.6
    RAG_TOP_K_PER_QUERY: int = 3

    # --- App ---
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    ENV: str = "dev"


settings = Settings()
