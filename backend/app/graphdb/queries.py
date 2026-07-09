"""
Read-side queries against the context graph.

`get_company_graph_full` replaces the old single-hop `get_company_graph`.
It assembles a multi-hop graph payload by calling targeted per-branch
functions (Option B from the audit doc) — one small, purpose-built query
per relationship path, then merges the results. Each node carries a `hop`
attribute (0 = Company, 1 = direct relations, 2 = second-degree) and a
`parent_id` (for hop-2 nodes) so the frontend can cluster them near their
parent in the concentric-ring layout.

`find_related_parties` and `find_shared_bank_accounts` are unchanged —
they're still used by Layer 3's triangulation logic.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.graphdb.neo4j_client import run_read


# ── Hop-1 base graph (Company + all direct neighbours) ───────────────────────

def get_company_graph(cin: str) -> Dict[str, Any]:
    """One-hop neighbourhood — kept for internal use; prefer get_company_graph_full for the API."""
    rows = run_read(
        """
        MATCH (c:Company {cin: $cin})
        OPTIONAL MATCH (c)-[r]->(n)
        RETURN c, collect({rel: type(r), node: n, labels: labels(n)}) AS neighbours
        """,
        cin=cin,
    )
    if not rows:
        return {"nodes": [], "edges": []}

    company_node = rows[0]["c"]
    nodes = [{"id": cin, "label": company_node.get("legal_name", cin), "type": "Company", "hop": 0, "props": dict(company_node)}]
    edges = []
    for nb in rows[0]["neighbours"]:
        if nb["node"] is None:
            continue
        node = nb["node"]
        node_type = nb["labels"][0] if nb["labels"] else "Unknown"
        node_id = (
            node.get("din") or node.get("gstin") or node.get("account_key")
            or node.get("profile_id") or node.get("snapshot_id")
        )
        node_label = node.get("name") or node.get("legal_name") or node.get("bank_name") or node_type
        nodes.append({"id": node_id, "label": node_label, "type": node_type, "hop": 1, "props": dict(node)})
        edges.append({"source": cin, "target": node_id, "type": nb["rel"]})

    return {"nodes": nodes, "edges": edges}


# ── Hop-2 targeted branch queries ─────────────────────────────────────────────

def get_ledger_counterparties(cin: str) -> Dict[str, List]:
    """Counterparty nodes hung off LedgerSnapshot (top debtors + creditors)."""
    rows = run_read(
        """
        MATCH (c:Company {cin: $cin})-[:REPORTED_LEDGER]->(l:LedgerSnapshot)-[r:HAS_COUNTERPARTY]->(cp:Counterparty)
        RETURN l.snapshot_id AS parent_id, cp, r.role AS edge_role
        """,
        cin=cin,
    )
    nodes, edges = [], []
    for row in rows:
        cp = row["cp"]
        cp_id = cp.get("counterparty_id")
        if not cp_id:
            continue
        label = cp.get("name") or cp_id
        nodes.append({
            "id": cp_id,
            "label": label,
            "type": "Counterparty",
            "hop": 2,
            "parent_id": row["parent_id"],
            "props": dict(cp),
        })
        edges.append({
            "source": row["parent_id"],
            "target": cp_id,
            "type": f"HAS_COUNTERPARTY",
        })
    return {"nodes": nodes, "edges": edges}


def get_bank_counterparties(cin: str) -> Dict[str, List]:
    """Counterparty nodes hung off BankAccount (top narration-extracted counterparties)."""
    rows = run_read(
        """
        MATCH (c:Company {cin: $cin})-[:HOLDS_ACCOUNT]->(b:BankAccount)-[r:HAS_COUNTERPARTY]->(cp:Counterparty)
        RETURN b.account_key AS parent_id, cp, r.direction AS edge_direction
        """,
        cin=cin,
    )
    nodes, edges = [], []
    for row in rows:
        cp = row["cp"]
        cp_id = cp.get("counterparty_id")
        if not cp_id:
            continue
        label = cp.get("name") or cp_id
        nodes.append({
            "id": cp_id,
            "label": label,
            "type": "Counterparty",
            "hop": 2,
            "parent_id": row["parent_id"],
            "props": dict(cp),
        })
        edges.append({
            "source": row["parent_id"],
            "target": cp_id,
            "type": "HAS_COUNTERPARTY",
        })
    return {"nodes": nodes, "edges": edges}


def get_loan_facilities(cin: str) -> Dict[str, List]:
    """LoanFacility nodes hung off BureauProfile."""
    rows = run_read(
        """
        MATCH (c:Company {cin: $cin})-[:HAS_BUREAU_PROFILE]->(p:BureauProfile)-[:HAS_FACILITY]->(f:LoanFacility)
        RETURN p.profile_id AS parent_id, f
        """,
        cin=cin,
    )
    nodes, edges = [], []
    for row in rows:
        fac = row["f"]
        fac_id = fac.get("facility_id")
        if not fac_id:
            continue
        label = fac.get("lender_name") or fac.get("facility_type") or "Facility"
        nodes.append({
            "id": fac_id,
            "label": label,
            "type": "LoanFacility",
            "hop": 2,
            "parent_id": row["parent_id"],
            "props": dict(fac),
        })
        edges.append({
            "source": row["parent_id"],
            "target": fac_id,
            "type": "HAS_FACILITY",
        })
    return {"nodes": nodes, "edges": edges}


def get_director_bureau_profiles(cin: str) -> Dict[str, List]:
    """PersonalBureauProfile nodes hung off Director nodes."""
    rows = run_read(
        """
        MATCH (c:Company {cin: $cin})-[:HAS_DIRECTOR]->(d:Director)-[:HAS_PERSONAL_BUREAU]->(pb:PersonalBureauProfile)
        RETURN d.din AS parent_id, pb
        """,
        cin=cin,
    )
    nodes, edges = [], []
    for row in rows:
        pb = row["pb"]
        pb_id = pb.get("personal_bureau_id")
        if not pb_id:
            continue
        label = pb.get("director_name") or "Personal CIBIL"
        nodes.append({
            "id": pb_id,
            "label": label,
            "type": "PersonalBureauProfile",
            "hop": 2,
            "parent_id": row["parent_id"],
            "props": dict(pb),
        })
        edges.append({
            "source": row["parent_id"],
            "target": pb_id,
            "type": "HAS_PERSONAL_BUREAU",
        })
    return {"nodes": nodes, "edges": edges}


def get_related_companies(cin: str) -> Dict[str, List]:
    """Other Company nodes reachable via RELATED_COMPANY (shared-director) edges.
    These appear at hop-2, parent = the Director node that connects them."""
    rows = run_read(
        """
        MATCH (c:Company {cin: $cin})-[:HAS_DIRECTOR]->(d:Director)<-[:HAS_DIRECTOR]-(other:Company)
        WHERE other.cin <> $cin
        RETURN d.din AS parent_id, other
        """,
        cin=cin,
    )
    nodes, edges = [], []
    seen = set()
    for row in rows:
        other = row["other"]
        other_cin = other.get("cin")
        if not other_cin or other_cin in seen:
            continue
        seen.add(other_cin)
        label = other.get("legal_name") or other_cin
        nodes.append({
            "id": other_cin,
            "label": label,
            "type": "Company",
            "hop": 2,
            "parent_id": row["parent_id"],
            "props": dict(other),
        })
        edges.append({
            "source": row["parent_id"],
            "target": other_cin,
            "type": "RELATED_COMPANY",
        })
    return {"nodes": nodes, "edges": edges}


def get_personal_loan_facilities(cin: str) -> Dict[str, List]:
    """LoanFacility nodes hung off PersonalBureauProfile (personal CIR loans)."""
    rows = run_read(
        """
        MATCH (c:Company {cin: $cin})-[:HAS_DIRECTOR]->(d:Director)
              -[:HAS_PERSONAL_BUREAU]->(pb:PersonalBureauProfile)-[:HAS_FACILITY]->(f:LoanFacility)
        RETURN pb.personal_bureau_id AS parent_id, f
        """,
        cin=cin,
    )
    nodes, edges = [], []
    for row in rows:
        fac = row["f"]
        fac_id = fac.get("facility_id")
        if not fac_id:
            continue
        label = fac.get("lender_name") or fac.get("facility_type") or "Personal Facility"
        nodes.append({
            "id": fac_id,
            "label": label,
            "type": "LoanFacility",
            "hop": 2,
            "parent_id": row["parent_id"],
            "props": dict(fac),
        })
        edges.append({
            "source": row["parent_id"],
            "target": fac_id,
            "type": "HAS_FACILITY",
        })
    return {"nodes": nodes, "edges": edges}


def get_credit_enquiries(cin: str) -> Dict[str, List]:
    """CreditEnquiry nodes hung off commercial BureauProfile or PersonalBureauProfile."""
    rows = run_read(
        """
        MATCH (c:Company {cin: $cin})-[:HAS_BUREAU_PROFILE]->(p:BureauProfile)-[:HAS_ENQUIRY]->(ce:CreditEnquiry)
        RETURN p.profile_id AS parent_id, ce
        UNION
        MATCH (c:Company {cin: $cin})-[:HAS_DIRECTOR]->(:Director)
              -[:HAS_PERSONAL_BUREAU]->(pb:PersonalBureauProfile)-[:HAS_ENQUIRY]->(ce:CreditEnquiry)
        RETURN pb.personal_bureau_id AS parent_id, ce
        """,
        cin=cin,
    )
    nodes, edges = [], []
    for row in rows:
        enq = row["ce"]
        enq_id = enq.get("enquiry_id")
        if not enq_id:
            continue
        label = f"Enq: {enq.get('lender_name') or enq.get('purpose') or 'Bureau Enquiry'}"
        nodes.append({
            "id": enq_id,
            "label": label,
            "type": "CreditEnquiry",
            "hop": 2,
            "parent_id": row["parent_id"],
            "props": dict(enq),
        })
        edges.append({
            "source": row["parent_id"],
            "target": enq_id,
            "type": "HAS_ENQUIRY",
        })
    return {"nodes": nodes, "edges": edges}


def count_recent_enquiries(profile_id: str, days: int = 30) -> int:
    """Bounded Cypher helper: count itemized enquiries on a profile within the last N days.

    Used by Layer 3 / velocity checks to detect sudden bursts of credit applications.
    """
    rows = run_read(
        """
        MATCH ({profile_id: $profile_id})-[:HAS_ENQUIRY]->(ce:CreditEnquiry)
        WHERE ce.enquiry_date IS NOT NULL AND ce.enquiry_date <> ''
          AND date(ce.enquiry_date) >= date() - duration({days: $days})
        RETURN count(ce) AS recent_count
        """,
        profile_id=profile_id,
        days=days,
    )
    return int(rows[0]["recent_count"]) if rows else 0


# ── Full multi-hop graph assembly ─────────────────────────────────────────────

def get_bank_risk_events(cin: str) -> Dict[str, List]:
    """BankRiskEvent nodes hung off BankAccount (itemized transaction risk flags)."""
    rows = run_read(
        """
        MATCH (c:Company {cin: $cin})-[:HOLDS_ACCOUNT]->(b:BankAccount)-[:HAS_RISK_EVENT]->(re:BankRiskEvent)
        RETURN b.account_key AS parent_id, re
        """,
        cin=cin,
    )
    nodes, edges = [], []
    for row in rows:
        re_node = row["re"]
        event_id = re_node.get("event_id")
        if not event_id:
            continue
        label = f"Risk: {re_node.get('event_type')} (₹{re_node.get('amount', 0)})"
        nodes.append({
            "id": event_id,
            "label": label,
            "type": "BankRiskEvent",
            "hop": 2,
            "parent_id": row["parent_id"],
            "props": dict(re_node),
        })
        edges.append({
            "source": row["parent_id"],
            "target": event_id,
            "type": "HAS_RISK_EVENT",
        })
    return {"nodes": nodes, "edges": edges}


def get_company_graph_full(cin: str) -> Dict[str, Any]:
    """Assembles a multi-hop graph payload for the frontend.

    Calls targeted per-branch query functions and merges their node/edge lists.
    Each node carries:
      - hop: 0 (Company), 1 (direct neighbours), 2 (second-degree)
      - parent_id: ID of the hop-1 node this hop-2 node hangs off (for layout clustering)
    """
    base = get_company_graph(cin)
    all_nodes: List[Dict] = list(base["nodes"])
    all_edges: List[Dict] = list(base["edges"])

    seen_ids = {n["id"] for n in all_nodes if n.get("id")}

    def merge_branch(branch_result: Dict) -> None:
        for node in branch_result.get("nodes", []):
            nid = node.get("id")
            if nid and nid not in seen_ids:
                all_nodes.append(node)
                seen_ids.add(nid)
        all_edges.extend(branch_result.get("edges", []))

    merge_branch(get_ledger_counterparties(cin))
    merge_branch(get_bank_counterparties(cin))
    merge_branch(get_bank_risk_events(cin))
    merge_branch(get_loan_facilities(cin))
    merge_branch(get_director_bureau_profiles(cin))
    merge_branch(get_personal_loan_facilities(cin))
    merge_branch(get_credit_enquiries(cin))
    merge_branch(get_related_companies(cin))

    return {"nodes": all_nodes, "edges": all_edges}





# ── Layer-3 fraud/triangulation queries (unchanged) ───────────────────────────

def find_related_parties(cin: str) -> List[Dict[str, Any]]:
    """Companies that share at least one director with the given Company -
    a real related-party / group-exposure signal."""
    rows = run_read(
        """
        MATCH (c:Company {cin: $cin})-[:HAS_DIRECTOR]->(d:Director)<-[:HAS_DIRECTOR]-(other:Company)
        WHERE other.cin <> $cin
        RETURN other.cin AS cin, other.legal_name AS legal_name,
               collect(DISTINCT d.name) AS shared_directors
        """,
        cin=cin,
    )
    return rows


def find_shared_bank_accounts(cin: str) -> List[Dict[str, Any]]:
    """Companies that hold the exact same bank account as this one - a much
    stronger fraud signal than shared directorship (legitimate group
    companies often share directors; they essentially never share an
    actual bank account with an 'unrelated' applicant)."""
    rows = run_read(
        """
        MATCH (c:Company {cin: $cin})-[:HOLDS_ACCOUNT]->(b:BankAccount)<-[:HOLDS_ACCOUNT]-(other:Company)
        WHERE other.cin <> $cin
        RETURN other.cin AS cin, other.legal_name AS legal_name,
               collect(DISTINCT b.account_key) AS shared_accounts
        """,
        cin=cin,
    )
    return rows


def case_summary(case_id: str) -> Dict[str, Any]:
    rows = run_read(
        """
        MATCH (c:Company {case_id: $case_id})
        OPTIONAL MATCH (c)-->(n)
        RETURN c.cin AS cin, c.legal_name AS legal_name, count(n) AS connected_nodes
        """,
        case_id=case_id,
    )
    return rows[0] if rows else {}


# ── Phase 3 — Multiple banking detection (query-only, no new extraction) ──────

def detect_multiple_banking(cin: str) -> List[Dict[str, Any]]:
    """Detect loan stacking: 2+ active CC/OD facilities from *distinct* lenders.

    Traversal is bounded at 2 hops: Company → BureauProfile → LoanFacility.
    Returns the list of matching facility rows if 2+ distinct lenders found,
    empty list otherwise.  Does NOT wire into Layer 4 rules — that is a
    business-rule decision to be confirmed separately.
    """
    rows = run_read(
        """
        MATCH (c:Company {cin: $cin})-[:HAS_BUREAU_PROFILE]->(p:BureauProfile)
              -[:HAS_FACILITY]->(f:LoanFacility)
        WHERE toLower(f.account_status) = 'active'
          AND toLower(f.facility_type) IN ['cc', 'od', 'cash credit', 'overdraft',
                                           'cash credit (cc)', 'overdraft (od)']
          AND f.lender_name <> ''
        RETURN f.lender_name      AS lender_name,
               f.facility_id     AS facility_id,
               f.facility_type   AS facility_type,
               f.sanctioned_amount   AS sanctioned_amount,
               f.outstanding_amount  AS outstanding_amount,
               f.dpd_bucket      AS dpd_bucket
        ORDER BY f.outstanding_amount DESC
        LIMIT 20
        """,
        cin=cin,
    )
    # Only flag when 2+ *distinct* lenders are present
    distinct_lenders = {r["lender_name"] for r in rows if r.get("lender_name")}
    if len(distinct_lenders) < 2:
        return []
    return [dict(r) for r in rows]


# ── Phase 5 — Counterparty ↔ GSTEntity resolution (query side) ───────────────

def find_counterparty_company_matches(cin: str) -> List[Dict[str, Any]]:
    """Return Counterparty nodes (from this company's ledger) that have been
    resolved to an existing GSTEntity in the graph via POSSIBLE_SAME_ENTITY_AS.

    This lets Layer 3 / the frontend surface: 'your top debtor is also a known
    GST-registered entity in our system — here is what we know about them.'
    Bounded at 3 hops: Company → LedgerSnapshot → Counterparty → GSTEntity.
    """
    rows = run_read(
        """
        MATCH (c:Company {cin: $cin})-[:REPORTED_LEDGER]->(l:LedgerSnapshot)
              -[:HAS_COUNTERPARTY]->(cp:Counterparty)
              -[m:POSSIBLE_SAME_ENTITY_AS]->(g:GSTEntity)
        RETURN cp.counterparty_id   AS counterparty_id,
               cp.name              AS counterparty_name,
               cp.gstin             AS gstin,
               cp.role              AS role,
               cp.total_invoice_value AS total_invoice_value,
               g.gstin              AS matched_gstin,
               g.legal_name         AS matched_legal_name,
               g.filing_status      AS matched_filing_status,
               g.gstr3b_annual_turnover AS matched_turnover,
               m.matched_at         AS matched_at
        ORDER BY cp.total_invoice_value DESC
        LIMIT 25
        """,
        cin=cin,
    )
    return [dict(r) for r in rows]




# ── Phase 6 — Facilities Guaranteed By Director ──────────────────────────────

def find_guaranteed_facilities(cin: str) -> List[Dict[str, Any]]:
    """Return credit facilities where a company director acts as a guarantor or co-borrower."""
    rows = run_read(
        """
        MATCH (c:Company {cin: $cin})-[:HAS_DIRECTOR]->(d:Director)
              <-[:GUARANTEED_BY]-(f:LoanFacility)
        RETURN d.name               AS director_name,
               d.din                AS din,
               f.lender_name        AS lender_name,
               f.facility_type      AS facility_type,
               f.sanctioned_amount  AS sanctioned_amount,
               f.outstanding_amount AS outstanding_amount,
               f.dpd_bucket         AS dpd_bucket,
               f.account_status     AS account_status,
               f.guarantor_name     AS guarantor_name
        ORDER BY f.outstanding_amount DESC
        LIMIT 25
        """,
        cin=cin,
    )
    return [dict(r) for r in rows]


