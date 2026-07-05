"""
Hybrid RAG (Retrieval-Augmented Generation) layer.

Replaces the original TF-IDF-only approach with a two-retriever architecture:

  Sparse retriever  — BM25 (rank_bm25). Handles exact keyword matches,
                      specific IDs (PAN, GSTIN, account numbers), and precise
                      numeric terms. Equivalent to what TF-IDF was doing but
                      with better term-frequency normalisation.

  Dense retriever   — sentence-transformers/all-MiniLM-L6-v2 embeddings.
                      Handles semantic similarity: a query for "financial
                      distress" will match text about "bounced cheques" and
                      "overdue receivables" even without exact keyword overlap.

  Fusion            — Reciprocal Rank Fusion (RRF) combines both ranked lists
                      into a single final ranking without needing to tune score
                      scales between the two retrievers.

Graceful degradation:
  - If sentence-transformers fails to load, the system falls back to BM25-only
    with no crash and no API change needed.
  - If BM25 is also unavailable (should never happen — it's pure Python), falls
    back to returning the first max_chars of the document.

Public API is IDENTICAL to the original rag.py:
  retrieve_relevant_context(source, full_text, max_chars=None) -> str

All callers (layer1_graph.py, scratch tests) need zero changes.

Design constraints preserved from original:
  - JSON documents skip chunking (chunking destroys JSON structure).
    They go through _summarize_json_text → hard-cap truncation.
  - Bureau reports are split by === section headers, each capped at 3,500 chars.
  - AGENT_RAG_QUERIES and SOURCE_MAX_CHARS are unchanged.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import numpy as np

from app.layer1.chunking import chunk_for_source
from app.layer1.embeddings import embed_query, embed_texts

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Agent-specific query topics (unchanged from original)
# ---------------------------------------------------------------------------

AGENT_RAG_QUERIES = {
    "bureau": [
        "score score rating cibil transunion CMR MSME rank credit vision",
        "exposure total exposure balance high credit sanctioned limit liability debt",
        "overdue overdue amount accounts 30 60 90 DPD days past due delinquency history write off",
        "enquiries inquiries last 6 months written off active accounts status",
    ],
    "banking": [
        "total credits total debits credits debits turnover transactions cash deposit ratio average balance",
        "cheque bounce bounce count return minimum balance observed account number current account cc od",
    ],
    "gst": [
        "gstin legal name registration date date of registration filing frequency filing status last filed",
        "GSTR-3B reported annual turnover GSTR-1 reported annual turnover late filings returns",
    ],
    "financials": [
        "revenue ebitda net profit profit after tax net worth total assets total liabilities debt equity ratio",
    ],
    "ledger": [
        "total sales total purchases debtor days creditor days top debtor concentration anchor risk overdue receivables",
    ],
    "kyc": [
        "legal name CIN PAN date of incorporation entity type registered address directors DIN KYC status",
    ],
}

# Per-source hard cap on retrieved context (chars). Unchanged from original.
SOURCE_MAX_CHARS: dict[str, int] = {
    "bureau": 5000,
    "banking": 4000,
    "gst": 9000,
    "financials": 3500,
    "ledger": 3500,
    "kyc": 3000,
}
DEFAULT_MAX_CHARS = 4000

# Retrieval config
_TOP_K_PER_QUERY = 3       # chunks retrieved per query per retriever
_RRF_K = 60                # RRF constant (standard choice; higher = smoother ranking)
_BM25_WEIGHT = 0.4         # relative weight of sparse results in RRF fusion
_DENSE_WEIGHT = 0.6        # relative weight of dense results in RRF fusion


# ---------------------------------------------------------------------------
# JSON preprocessing (unchanged from original)
# ---------------------------------------------------------------------------

def _summarize_json_text(text: str) -> str:
    """
    If text is valid JSON, prune large transaction details/invoice lists
    to keep only the key summary objects and compliance history.

    Key design decision: entity_profile and overall summaries (containing turnover)
    are placed FIRST in the output so they survive the hard-cap truncation.
    Compliance (which can be very long) is placed last and trimmed.
    """
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            # Build output in priority order — most critical fields first
            # so they survive the 9000-char hard cap.
            ordered_keys = [
                "entity_profile",              # gstin, legal_name, registration_date
                "gstr3b_overall_summary",       # GSTR-3B turnover (taxable_value)
                "gstr1_overall_summary",        # GSTR-1 turnover
                "annual_summary",               # annual_sales, annual_purchases
                "business_summary",             # high-level business info
                "gstr1_vs_gstr3b",              # cross-comparison
            ]
            summary = {}
            for k in ordered_keys:
                if k in data:
                    summary[k] = data[k]

            # Add compliance but truncated to last 12 entries (most recent)
            if "compliance" in data:
                comp = data["compliance"]
                if isinstance(comp, list) and len(comp) > 12:
                    summary["compliance"] = comp[-12:]
                else:
                    summary["compliance"] = comp

            return json.dumps(summary, indent=2)
    except Exception:
        pass
    return text


# ---------------------------------------------------------------------------
# BM25 sparse retriever
# ---------------------------------------------------------------------------

def _bm25_retrieve(chunks: list[str], queries: list[str], top_k: int) -> dict[int, int]:
    """
    Run BM25 retrieval for all queries and return a dict mapping
    chunk_index -> sparse_rank_sum (lower = better).

    Returns {} if rank_bm25 is unavailable.
    """
    try:
        from rank_bm25 import BM25Okapi  # type: ignore
    except ImportError:
        logger.warning("RAG: rank_bm25 not installed. BM25 retrieval disabled.")
        return {}

    tokenised = [c.lower().split() for c in chunks]
    bm25 = BM25Okapi(tokenised)

    rank_accumulator: dict[int, int] = {}
    for query in queries:
        scores = bm25.get_scores(query.lower().split())
        ranked = np.argsort(scores)[::-1][:top_k]
        for rank, idx in enumerate(ranked):
            if scores[idx] > 0:
                rank_accumulator[int(idx)] = rank_accumulator.get(int(idx), 0) + rank + 1
    return rank_accumulator


# ---------------------------------------------------------------------------
# Dense semantic retriever
# ---------------------------------------------------------------------------

def _dense_retrieve(chunks: list[str], queries: list[str], top_k: int) -> dict[int, int]:
    """
    Run dense embedding retrieval for all queries and return a dict mapping
    chunk_index -> dense_rank_sum (lower = better).

    Returns {} if embedding model is unavailable (graceful degradation).
    """
    chunk_embeddings = embed_texts(chunks)
    if chunk_embeddings is None:
        return {}

    rank_accumulator: dict[int, int] = {}
    for query in queries:
        q_vec = embed_query(query)
        if q_vec is None:
            continue
        # Cosine similarity via dot product on normalised vectors
        chunk_norms = np.linalg.norm(chunk_embeddings, axis=1, keepdims=True) + 1e-10
        q_norm = np.linalg.norm(q_vec) + 1e-10
        sims = (chunk_embeddings / chunk_norms) @ (q_vec / q_norm)
        ranked = np.argsort(sims)[::-1][:top_k]
        for rank, idx in enumerate(ranked):
            if sims[idx] > 0.0:
                rank_accumulator[int(idx)] = rank_accumulator.get(int(idx), 0) + rank + 1
    return rank_accumulator


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion
# ---------------------------------------------------------------------------

def _rrf_fuse(
    sparse_ranks: dict[int, int],
    dense_ranks: dict[int, int],
    all_indices: list[int],
    k: int = _RRF_K,
) -> list[int]:
    """
    Combine sparse and dense rankings using Reciprocal Rank Fusion.

    RRF score for doc d = Σ ( weight / (k + rank(d)) )

    Higher RRF score = more relevant. Returns indices sorted best-first.
    """
    rrf_scores: dict[int, float] = {}
    for idx in all_indices:
        score = 0.0
        if idx in sparse_ranks:
            score += _BM25_WEIGHT / (k + sparse_ranks[idx])
        if idx in dense_ranks:
            score += _DENSE_WEIGHT / (k + dense_ranks[idx])
        if score > 0.0:
            rrf_scores[idx] = score
    return sorted(rrf_scores, key=lambda i: rrf_scores[i], reverse=True)


# ---------------------------------------------------------------------------
# HybridRAG — the main retrieval class
# ---------------------------------------------------------------------------

class HybridRAG:
    """
    Retrieves the most relevant text chunks for a set of queries using a
    hybrid sparse+dense approach with RRF fusion.

    Chunking is delegated to layer1.chunking.chunk_for_source, which picks
    the right strategy (semantic vs tabular) based on the source type.
    """

    def __init__(self, source: str, text: str):
        self.source = source
        self.chunks = chunk_for_source(source, text)
        logger.debug(
            "HybridRAG: source='%s', produced %d chunks from %d chars of text.",
            source, len(self.chunks), len(text),
        )

    def retrieve(self, queries: list[str], top_k: int = _TOP_K_PER_QUERY) -> list[str]:
        """
        Return the top-ranked unique chunks for the given queries,
        ordered by their original document position to preserve narrative flow.
        """
        if not self.chunks:
            return []

        all_indices = list(range(len(self.chunks)))

        sparse_ranks = _bm25_retrieve(self.chunks, queries, top_k)
        dense_ranks = _dense_retrieve(self.chunks, queries, top_k)

        if not sparse_ranks and not dense_ranks:
            logger.warning(
                "HybridRAG: Both retrievers returned empty results for source '%s'. "
                "Returning first %d chunks.",
                self.source, top_k,
            )
            return self.chunks[:top_k]

        fused = _rrf_fuse(sparse_ranks, dense_ranks, all_indices)

        # Limit to top_k unique chunks, then sort by original position
        selected_indices = sorted(fused[:top_k * len(queries)])
        # Deduplicate while preserving order
        seen: set[int] = set()
        ordered: list[int] = []
        for idx in selected_indices:
            if idx not in seen:
                seen.add(idx)
                ordered.append(idx)

        return [self.chunks[i] for i in ordered]


# ---------------------------------------------------------------------------
# Public entry point (API-compatible with original rag.py)
# ---------------------------------------------------------------------------

def retrieve_relevant_context(
    source: str, full_text: str, max_chars: int | None = None
) -> str:
    """
    Hybrid RAG entry point. Identical public API to the original rag.py.

    Pipeline:
      1. JSON → structural pruning (_summarize_json_text), then hard-cap.
         No chunking — chunking destroys JSON structure.
      2. Bureau plain-text → section-prefix pruning (=== splits), then hard-cap.
      3. All other plain-text → HybridRAG (BM25 + dense embeddings + RRF),
         then hard-cap.

    Always hard-caps the output to max_chars regardless of retrieval path.
    """
    is_json = full_text.strip().startswith("{") or full_text.strip().startswith("[")

    # 1. Prune large arrays from JSON (gst.json etc.) to keep structured summaries
    if is_json:
        full_text = _summarize_json_text(full_text)

    max_chars = max_chars or SOURCE_MAX_CHARS.get(source, DEFAULT_MAX_CHARS)

    # 2. If within budget, return as-is (nothing to do)
    if len(full_text) <= max_chars:
        return full_text

    # 3. Bureau: split by === sections and keep the first 3,500 chars of each.
    #    Score summaries and credit scores are always at the top of each section.
    if source == "bureau":
        sections = full_text.split("=== ")
        pruned_sections = []
        for sec in sections:
            if not sec.strip():
                continue
            pruned_sections.append("=== " + sec[:3500])
        retrieved_text = "\n\n".join(pruned_sections)
        logger.info(
            "RAG: Bureau section-pruned: %d → %d chars.",
            len(full_text), len(retrieved_text),
        )
        return retrieved_text[:max_chars]

    # 4. JSON too large even after pruning → hard-cap from the top.
    #    Structural keys are always at the top after _summarize_json_text ordering.
    if is_json:
        logger.info(
            "RAG: JSON source '%s' still exceeds %d chars after pruning — hard-capping.",
            source, max_chars,
        )
        return full_text[:max_chars]

    # 5. Plain text → Hybrid RAG retrieval
    logger.info(
        "RAG: Text size (%d chars) exceeds threshold (%d). "
        "Applying HybridRAG for source: %s.",
        len(full_text), max_chars, source,
    )

    queries = AGENT_RAG_QUERIES.get(source, [f"extract data for {source}"])
    rag = HybridRAG(source, full_text)
    selected_chunks = rag.retrieve(queries, top_k=_TOP_K_PER_QUERY)

    if not selected_chunks:
        logger.warning(
            "RAG: No chunks retrieved for '%s'. Defaulting to first %d chars.",
            source, max_chars,
        )
        return full_text[:max_chars]

    retrieved_text = "\n\n... [RAG Context Gap] ...\n\n".join(selected_chunks)

    # Hard cap: never send more than max_chars to the LLM
    if len(retrieved_text) > max_chars:
        retrieved_text = retrieved_text[:max_chars]
        logger.info(
            "RAG: Retrieved context for '%s' hard-capped at %d chars.", source, max_chars
        )

    logger.info(
        "RAG: Reduced '%s' context from %d → %d characters.",
        source, len(full_text), len(retrieved_text),
    )
    return retrieved_text
