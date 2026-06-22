"""
Uniqueness constraints for every node type in the context graph. Run
ensure_constraints() once at startup (main.py does this) - it's idempotent,
so re-running it on every boot is fine.
"""
from __future__ import annotations

import logging

from app.graphdb.neo4j_client import run_write

logger = logging.getLogger(__name__)

CONSTRAINTS = [
    "CREATE CONSTRAINT company_cin IF NOT EXISTS FOR (c:Company) REQUIRE c.cin IS UNIQUE",
    "CREATE CONSTRAINT director_din IF NOT EXISTS FOR (d:Director) REQUIRE d.din IS UNIQUE",
    "CREATE CONSTRAINT gst_entity_gstin IF NOT EXISTS FOR (g:GSTEntity) REQUIRE g.gstin IS UNIQUE",
    "CREATE CONSTRAINT bank_account_key IF NOT EXISTS FOR (b:BankAccount) REQUIRE b.account_key IS UNIQUE",
    "CREATE CONSTRAINT bureau_profile_id IF NOT EXISTS FOR (p:BureauProfile) REQUIRE p.profile_id IS UNIQUE",
    "CREATE CONSTRAINT financials_snapshot_id IF NOT EXISTS FOR (f:FinancialsSnapshot) REQUIRE f.snapshot_id IS UNIQUE",
    "CREATE CONSTRAINT ledger_snapshot_id IF NOT EXISTS FOR (l:LedgerSnapshot) REQUIRE l.snapshot_id IS UNIQUE",
]


def ensure_constraints() -> None:
    for stmt in CONSTRAINTS:
        try:
            run_write(stmt)
        except Exception as e:
            # Don't crash app startup if Neo4j isn't reachable yet / constraint
            # syntax differs slightly across Neo4j versions - log and move on.
            logger.warning("Could not apply constraint (%s): %s", stmt, e)
