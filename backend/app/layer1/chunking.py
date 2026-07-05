"""
Document chunking strategies for the Hybrid RAG layer.

Three strategies available, selected based on document type:

  1. semantic_chunk  — splits on structural boundaries (===, ---, blank lines).
                       Best for bureau reports, credit memos, GST summaries.
  2. tabular_chunk   — splits line-by-line, preserving each row as a unit.
                       Best for banking statements and ledger tables.
  3. add_overlap     — post-processing step that copies the last N lines of each
                       chunk into the start of the next, so cross-boundary
                       context is not lost.

Design note: JSON documents bypass all chunking (handled separately in rag.py
via _summarize_json_text) because chunking destroys JSON structure.
"""
from __future__ import annotations

import re


# ---------------------------------------------------------------------------
# Semantic chunking — respects section and paragraph boundaries
# ---------------------------------------------------------------------------

_SECTION_PATTERN = re.compile(r"^(?:===|---|###|\*\*\*)", re.MULTILINE)


def semantic_chunk(text: str, max_chunk_chars: int = 500) -> list[str]:
    """
    Split text on structural boundaries first, then enforce a max size.

    Boundaries recognised (in priority order):
      - Lines starting with === or --- or ### (section headers in bureau/GST reports)
      - Two or more consecutive blank lines (paragraph breaks)
      - Single blank lines (softer paragraph break, used only when needed)

    If a resulting section still exceeds max_chunk_chars, it is recursively
    split by single blank lines, then by raw character count as a last resort.
    """
    # Step 1: hard section splits (===, ---, ###)
    raw_sections: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if _SECTION_PATTERN.match(line) and current:
            raw_sections.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        raw_sections.append("\n".join(current))

    # Step 2: further split oversized sections on double blank lines, then
    # single blank lines, then hard char limit
    chunks: list[str] = []
    for section in raw_sections:
        if len(section) <= max_chunk_chars:
            if section.strip():
                chunks.append(section.strip())
        else:
            sub = _split_by_blank_lines(section, max_chunk_chars, double_only=True)
            for s in sub:
                if len(s) <= max_chunk_chars:
                    if s.strip():
                        chunks.append(s.strip())
                else:
                    sub2 = _split_by_blank_lines(s, max_chunk_chars, double_only=False)
                    for s2 in sub2:
                        if len(s2) <= max_chunk_chars:
                            if s2.strip():
                                chunks.append(s2.strip())
                        else:
                            # Last resort: hard character split
                            for i in range(0, len(s2), max_chunk_chars):
                                piece = s2[i : i + max_chunk_chars].strip()
                                if piece:
                                    chunks.append(piece)

    return [c for c in chunks if c]


def _split_by_blank_lines(
    text: str, max_chunk_chars: int, double_only: bool
) -> list[str]:
    """Split text on blank lines (double or single depending on flag)."""
    pattern = r"\n{2,}" if double_only else r"\n"
    parts = re.split(pattern, text)
    result: list[str] = []
    current_lines: list[str] = []
    current_len = 0

    for part in parts:
        part = part.strip()
        if not part:
            continue
        if current_len + len(part) + 1 > max_chunk_chars and current_lines:
            result.append("\n\n".join(current_lines))
            current_lines = [part]
            current_len = len(part)
        else:
            current_lines.append(part)
            current_len += len(part) + 1

    if current_lines:
        result.append("\n\n".join(current_lines))
    return result


# ---------------------------------------------------------------------------
# Tabular chunking — line-by-line (for bank statements, ledgers)
# ---------------------------------------------------------------------------

def tabular_chunk(text: str, chunk_lines: int = 30, overlap_lines: int = 5) -> list[str]:
    """
    Split tabular text into chunks of `chunk_lines` lines with `overlap_lines`
    lines of overlap between adjacent chunks.

    This preserves the row-integrity of bank statements and ledger tables —
    each line is a full transaction record and must not be cut mid-line.
    """
    lines = [ln for ln in text.splitlines()]  # keep blank lines for spacing
    chunks: list[str] = []
    i = 0
    while i < len(lines):
        end = min(i + chunk_lines, len(lines))
        chunk = "\n".join(lines[i:end]).strip()
        if chunk:
            chunks.append(chunk)
        # Move forward, keeping overlap
        i += chunk_lines - overlap_lines
        if i >= len(lines):
            break
    return chunks


# ---------------------------------------------------------------------------
# Overlap injection (post-processing, source-agnostic)
# ---------------------------------------------------------------------------

def add_overlap(chunks: list[str], overlap_lines: int = 2) -> list[str]:
    """
    Copy the last `overlap_lines` lines of each chunk to the start of the
    next chunk, so retrieval never loses context at a boundary.

    Applied after semantic_chunk when we want boundary-awareness without
    changing the chunking strategy.
    """
    if len(chunks) <= 1:
        return chunks
    result: list[str] = [chunks[0]]
    for i in range(1, len(chunks)):
        tail = "\n".join(chunks[i - 1].splitlines()[-overlap_lines:])
        result.append(tail + "\n" + chunks[i])
    return result


# ---------------------------------------------------------------------------
# Source-aware chunk dispatcher
# ---------------------------------------------------------------------------

TABULAR_SOURCES = {"banking", "ledger"}


def chunk_for_source(source: str, text: str, max_chunk_chars: int = 500) -> list[str]:
    """
    Select the right chunking strategy for a given document source and apply it.

    - banking / ledger  → tabular_chunk (preserves row integrity)
    - everything else   → semantic_chunk + add_overlap
    """
    if source in TABULAR_SOURCES:
        return tabular_chunk(text, chunk_lines=25, overlap_lines=4)
    else:
        chunks = semantic_chunk(text, max_chunk_chars=max_chunk_chars)
        return add_overlap(chunks, overlap_lines=2)
