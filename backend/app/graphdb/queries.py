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


# ── Full multi-hop graph assembly ─────────────────────────────────────────────

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
    merge_branch(get_loan_facilities(cin))
    merge_branch(get_director_bureau_profiles(cin))
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
