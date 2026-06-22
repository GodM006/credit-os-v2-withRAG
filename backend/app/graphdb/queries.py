"""
Read-side queries against the context graph.

`find_related_parties` is the concrete payoff of using a graph DB here: it's
a one-hop query in Cypher (find other Companies sharing a Director) that
would be a much uglier multi-join in a relational schema, and it's exactly
the kind of cross-entity signal Layer 3's fraud/triangulation logic wants.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.graphdb.neo4j_client import run_read


def get_company_graph(cin: str) -> Dict[str, Any]:
    """Returns the full one-hop neighbourhood of a Company as nodes + edges,
    shaped for a frontend graph viewer (id/label/type per node, source/target/type per edge)."""
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
    nodes = [{"id": cin, "label": company_node.get("legal_name", cin), "type": "Company", "props": dict(company_node)}]
    edges = []
    for nb in rows[0]["neighbours"]:
        if nb["node"] is None:
            continue
        node = nb["node"]
        node_type = nb["labels"][0] if nb["labels"] else "Unknown"
        node_id = node.get("din") or node.get("gstin") or node.get("account_key") or node.get("profile_id") or node.get("snapshot_id")
        node_label = node.get("name") or node.get("legal_name") or node.get("bank_name") or node_type
        nodes.append({"id": node_id, "label": node_label, "type": node_type, "props": dict(node)})
        edges.append({"source": cin, "target": node_id, "type": nb["rel"]})

    return {"nodes": nodes, "edges": edges}


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
    actual bank account with an "unrelated" applicant)."""
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
