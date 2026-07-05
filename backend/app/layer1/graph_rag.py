"""
GraphRAG context enrichment for Layer 1 agents.

Queries the Neo4j knowledge graph to build a structured context block that is
prepended to the retrieved document text before sending it to the LLM extraction
agents. This gives the LLM awareness of cross-entity relationships that pure
document-level retrieval cannot provide.

Context block includes:
  - The company's own graph neighbourhood (directors, GST entity, bank accounts)
  - Related parties (companies sharing a director) — a group-exposure signal
  - Shared bank accounts (shell company / structuring signal)
  - Historical fraud signals and policy outcomes for related entities

Design decisions:
  - If Neo4j is unavailable, returns an empty string silently. The agent pipeline
    is already resilient to missing context (see layer3/fraud_signals.py).
  - Output is plain English text, not JSON, so the LLM can read it naturally
    alongside the document context.
  - Depth is intentionally limited to 1-hop relationships to avoid pulling in
    irrelevant distant connections that could distort extraction.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _safe_str(val: Any) -> str:
    return str(val) if val is not None else "unknown"


def _format_currency(val: Any) -> str:
    try:
        return f"Rs {float(val):,.0f}"
    except (TypeError, ValueError):
        return "unknown"


# ---------------------------------------------------------------------------
# Individual context builders
# ---------------------------------------------------------------------------

def _build_company_context(cin: str) -> str:
    """Pull the company's own node properties from Neo4j."""
    try:
        from app.graphdb.neo4j_client import run_read

        rows = run_read(
            """
            MATCH (c:Company {cin: $cin})
            RETURN c.legal_name AS legal_name,
                   c.entity_type AS entity_type,
                   c.pan AS pan,
                   c.incorporation_date AS incorporation_date,
                   c.registered_address AS registered_address,
                   c.kyc_doc_status AS kyc_doc_status
            """,
            cin=cin,
        )
        if not rows:
            return ""
        r = rows[0]
        lines = [
            f"Company: {_safe_str(r.get('legal_name'))} ({_safe_str(r.get('entity_type'))})",
            f"  PAN: {_safe_str(r.get('pan'))}  |  CIN: {cin}",
            f"  Incorporated: {_safe_str(r.get('incorporation_date'))}",
            f"  Address: {_safe_str(r.get('registered_address'))}",
            f"  KYC doc status: {_safe_str(r.get('kyc_doc_status'))}",
        ]
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("GraphRAG: _build_company_context failed for CIN '%s': %s", cin, exc)
        return ""


def _build_director_context(cin: str) -> str:
    """List directors linked to this company in the graph."""
    try:
        from app.graphdb.neo4j_client import run_read

        rows = run_read(
            """
            MATCH (c:Company {cin: $cin})-[:HAS_DIRECTOR]->(d:Director)
            RETURN d.name AS name, d.din AS din, d.designation AS designation
            """,
            cin=cin,
        )
        if not rows:
            return ""
        lines = ["Directors on record:"]
        for r in rows:
            lines.append(
                f"  - {_safe_str(r.get('name'))} (DIN: {_safe_str(r.get('din'))}, "
                f"{_safe_str(r.get('designation'))})"
            )
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("GraphRAG: _build_director_context failed: %s", exc)
        return ""


def _build_related_party_context(cin: str) -> str:
    """Find companies sharing a director — group-exposure signal."""
    try:
        from app.graphdb.queries import find_related_parties

        related = find_related_parties(cin)
        if not related:
            return ""
        lines = [
            f"⚠ RELATED PARTY ALERT: This company shares directors with "
            f"{len(related)} other entity/entities:"
        ]
        for r in related:
            shared = ", ".join(r.get("shared_directors") or [])
            lines.append(
                f"  - {_safe_str(r.get('legal_name'))} (CIN: {_safe_str(r.get('cin'))}) "
                f"via shared director(s): {shared}"
            )
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("GraphRAG: _build_related_party_context failed: %s", exc)
        return ""


def _build_shared_account_context(cin: str) -> str:
    """Find companies sharing a bank account — strong fraud signal."""
    try:
        from app.graphdb.queries import find_shared_bank_accounts

        shared_accs = find_shared_bank_accounts(cin)
        if not shared_accs:
            return ""
        lines = [
            f"🚨 SHARED BANK ACCOUNT ALERT: This company shares bank account(s) with "
            f"{len(shared_accs)} other entity/entities (possible shell / structuring pattern):"
        ]
        for r in shared_accs:
            accounts = ", ".join(r.get("shared_accounts") or [])
            lines.append(
                f"  - {_safe_str(r.get('legal_name'))} (CIN: {_safe_str(r.get('cin'))}) "
                f"— shared account(s): {accounts}"
            )
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("GraphRAG: _build_shared_account_context failed: %s", exc)
        return ""


def _build_bureau_context(cin: str) -> str:
    """Pull bureau profile from graph for this company."""
    try:
        from app.graphdb.neo4j_client import run_read

        rows = run_read(
            """
            MATCH (c:Company {cin: $cin})-[:HAS_BUREAU_PROFILE]->(p:BureauProfile)
            RETURN p.bureau_score AS bureau_score,
                   p.total_exposure AS total_exposure,
                   p.overdue_amount AS overdue_amount,
                   p.dpd_90_plus AS dpd_90_plus,
                   p.written_off_accounts AS written_off_accounts,
                   p.enquiries_last_6m AS enquiries_last_6m
            """,
            cin=cin,
        )
        if not rows:
            return ""
        r = rows[0]
        lines = [
            "Bureau profile (from graph):",
            f"  Score: {_safe_str(r.get('bureau_score'))}  |  "
            f"Total exposure: {_format_currency(r.get('total_exposure'))}",
            f"  Overdue: {_format_currency(r.get('overdue_amount'))}  |  "
            f"90+ DPD accounts: {_safe_str(r.get('dpd_90_plus'))}  |  "
            f"Written-off: {_safe_str(r.get('written_off_accounts'))}",
            f"  Enquiries last 6m: {_safe_str(r.get('enquiries_last_6m'))}",
        ]
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("GraphRAG: _build_bureau_context failed: %s", exc)
        return ""


def _build_financials_context(cin: str) -> str:
    """Pull the most recent financials snapshot from graph."""
    try:
        from app.graphdb.neo4j_client import run_read

        rows = run_read(
            """
            MATCH (c:Company {cin: $cin})-[:REPORTED_FINANCIALS]->(f:FinancialsSnapshot)
            RETURN f.period AS period,
                   f.revenue AS revenue,
                   f.ebitda AS ebitda,
                   f.net_profit AS net_profit,
                   f.net_worth AS net_worth,
                   f.debt_equity_ratio AS debt_equity_ratio,
                   f.is_audited AS is_audited
            ORDER BY f.period DESC LIMIT 1
            """,
            cin=cin,
        )
        if not rows:
            return ""
        r = rows[0]
        audited = "Audited" if r.get("is_audited") else "Unaudited"
        lines = [
            f"Financials ({_safe_str(r.get('period'))}, {audited}):",
            f"  Revenue: {_format_currency(r.get('revenue'))}  |  "
            f"EBITDA: {_format_currency(r.get('ebitda'))}  |  "
            f"Net Profit: {_format_currency(r.get('net_profit'))}",
            f"  Net Worth: {_format_currency(r.get('net_worth'))}  |  "
            f"D/E Ratio: {_safe_str(r.get('debt_equity_ratio'))}",
        ]
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("GraphRAG: _build_financials_context failed: %s", exc)
        return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_entity_context(cin: str) -> str:
    """
    Build a plain-English context block from the Neo4j graph for the given CIN.

    Returns a multi-line string suitable for prepending to the document context
    sent to Layer 1 extraction agents. Returns empty string if Neo4j is
    unavailable or if no data exists for this CIN.

    The block format is deliberately readable prose/bullet points so the LLM
    can incorporate it naturally alongside the raw document text.
    """
    sections: list[str] = []

    company_ctx = _build_company_context(cin)
    if company_ctx:
        sections.append(company_ctx)

    director_ctx = _build_director_context(cin)
    if director_ctx:
        sections.append(director_ctx)

    bureau_ctx = _build_bureau_context(cin)
    if bureau_ctx:
        sections.append(bureau_ctx)

    financials_ctx = _build_financials_context(cin)
    if financials_ctx:
        sections.append(financials_ctx)

    # Risk signals — placed last so they are visually prominent
    related_ctx = _build_related_party_context(cin)
    if related_ctx:
        sections.append(related_ctx)

    shared_acc_ctx = _build_shared_account_context(cin)
    if shared_acc_ctx:
        sections.append(shared_acc_ctx)

    if not sections:
        logger.debug("GraphRAG: No graph context found for CIN '%s'.", cin)
        return ""

    header = f"=== KNOWLEDGE GRAPH CONTEXT (CIN: {cin}) ==="
    footer = "=== END GRAPH CONTEXT ==="
    return "\n".join([header] + sections + [footer])
