"""
Takes Layer 1's `source_jsons` for a case and projects it into the Neo4j
context graph: Company, Director, GSTEntity, BankAccount, BureauProfile,
FinancialsSnapshot, LedgerSnapshot nodes, joined by HAS_DIRECTOR, FILED_GST,
HOLDS_ACCOUNT, HAS_BUREAU_PROFILE, REPORTED_FINANCIALS, REPORTED_LEDGER.

Honest limitation: Layer 1's bureau/financials/ledger agents return
case-level aggregates, not itemized loans/invoices/counterparties, so the
diagram's Loan/Invoice/Supplier/Customer node types and the OWES_DEBT /
SUPPLIES_TO relationship types aren't populated yet. BureauProfile /
FinancialsSnapshot / LedgerSnapshot stand in for them until Layer 1 is
extended to itemized extraction. RELATED_PARTY *is* implemented, derived
from directors who appear on more than one Company (see queries.py).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from app.graphdb.neo4j_client import run_write


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_case_to_graph(case_id: str, source_jsons: Dict[str, Any]) -> Dict[str, Any]:
    summary = {"nodes_written": [], "relationships_written": [], "skipped": [], "company_cin": None}
    ingested_at = _now()

    kyc = (source_jsons.get("kyc") or {}).get("data")
    if not kyc:
        summary["skipped"].append("kyc missing/invalid - cannot anchor a Company node without a CIN")
        return summary

    cin = kyc["cin"]
    summary["company_cin"] = cin

    run_write(
        """
        MERGE (c:Company {cin: $cin})
        SET c.legal_name = $legal_name,
            c.pan = $pan,
            c.incorporation_date = $incorporation_date,
            c.entity_type = $entity_type,
            c.registered_address = $registered_address,
            c.kyc_doc_status = $kyc_doc_status,
            c.case_id = $case_id,
            c.ingested_at = $ingested_at
        """,
        cin=cin,
        legal_name=kyc["legal_name"],
        pan=kyc["pan"],
        incorporation_date=kyc["incorporation_date"],
        entity_type=kyc["entity_type"],
        registered_address=kyc["registered_address"],
        kyc_doc_status=kyc["kyc_doc_status"],
        case_id=case_id,
        ingested_at=ingested_at,
    )
    summary["nodes_written"].append("Company:1")

    directors = kyc.get("directors") or []
    for director in directors:
        run_write(
            """
            MERGE (d:Director {din: $din})
            SET d.name = $name, d.designation = $designation
            WITH d
            MATCH (c:Company {cin: $cin})
            MERGE (c)-[:HAS_DIRECTOR]->(d)
            """,
            din=director["din"], name=director["name"], designation=director["designation"], cin=cin,
        )
    if directors:
        summary["nodes_written"].append(f"Director:{len(directors)}")
        summary["relationships_written"].append(f"HAS_DIRECTOR:{len(directors)}")

    gst = (source_jsons.get("gst") or {}).get("data")
    if gst:
        run_write(
            """
            MERGE (g:GSTEntity {gstin: $gstin})
            SET g.legal_name = $legal_name,
                g.registration_date = $registration_date,
                g.filing_frequency = $filing_frequency,
                g.filing_status = $filing_status,
                g.last_filed_period = $last_filed_period,
                g.gstr3b_annual_turnover = $gstr3b_annual_turnover,
                g.gstr1_annual_turnover = $gstr1_annual_turnover,
                g.vintage_months = $vintage_months,
                g.late_filings_last_12m = $late_filings_last_12m,
                g.case_id = $case_id,
                g.ingested_at = $ingested_at
            WITH g
            MATCH (c:Company {cin: $cin})
            MERGE (c)-[:FILED_GST]->(g)
            """,
            cin=cin, case_id=case_id, ingested_at=ingested_at, **gst,
        )
        summary["nodes_written"].append("GSTEntity:1")
        summary["relationships_written"].append("FILED_GST:1")
    else:
        summary["skipped"].append("gst missing/invalid")

    banking = (source_jsons.get("banking") or {}).get("data")
    if banking:
        accounts = banking.get("accounts") or [{"bank_name": "unknown", "account_type": "current", "account_number_masked": "XXXX0000"}]
        for acc in accounts:
            account_key = f"{acc['bank_name']}:{acc['account_number_masked']}"
            run_write(
                """
                MERGE (b:BankAccount {account_key: $account_key})
                SET b.bank_name = $bank_name,
                    b.account_type = $account_type,
                    b.statement_period_start = $statement_period_start,
                    b.statement_period_end = $statement_period_end,
                    b.total_credits = $total_credits,
                    b.total_debits = $total_debits,
                    b.avg_monthly_balance = $avg_monthly_balance,
                    b.min_balance = $min_balance,
                    b.bounce_count = $bounce_count,
                    b.inferred_annual_turnover = $inferred_annual_turnover,
                    b.cash_deposit_ratio = $cash_deposit_ratio,
                    b.case_id = $case_id,
                    b.ingested_at = $ingested_at
                WITH b
                MATCH (c:Company {cin: $cin})
                MERGE (c)-[:HOLDS_ACCOUNT]->(b)
                """,
                account_key=account_key,
                bank_name=acc["bank_name"],
                account_type=acc["account_type"],
                statement_period_start=banking["statement_period_start"],
                statement_period_end=banking["statement_period_end"],
                total_credits=banking["total_credits"],
                total_debits=banking["total_debits"],
                avg_monthly_balance=banking["avg_monthly_balance"],
                min_balance=banking["min_balance"],
                bounce_count=banking["bounce_count"],
                inferred_annual_turnover=banking["inferred_annual_turnover"],
                cash_deposit_ratio=banking.get("cash_deposit_ratio"),
                case_id=case_id,
                ingested_at=ingested_at,
                cin=cin,
            )
        summary["nodes_written"].append(f"BankAccount:{len(accounts)}")
        summary["relationships_written"].append(f"HOLDS_ACCOUNT:{len(accounts)}")
    else:
        summary["skipped"].append("banking missing/invalid")

    bureau = (source_jsons.get("bureau") or {}).get("data")
    if bureau:
        profile_id = f"{case_id}:bureau"
        run_write(
            """
            MERGE (p:BureauProfile {profile_id: $profile_id})
            SET p.entity_type = $entity_type,
                p.bureau_score = $bureau_score,
                p.total_exposure = $total_exposure,
                p.overdue_amount = $overdue_amount,
                p.dpd_30 = $dpd_30,
                p.dpd_60 = $dpd_60,
                p.dpd_90_plus = $dpd_90_plus,
                p.enquiries_last_6m = $enquiries_last_6m,
                p.written_off_accounts = $written_off_accounts,
                p.active_accounts = $active_accounts,
                p.case_id = $case_id,
                p.ingested_at = $ingested_at
            WITH p
            MATCH (c:Company {cin: $cin})
            MERGE (c)-[:HAS_BUREAU_PROFILE]->(p)
            """,
            profile_id=profile_id, cin=cin, case_id=case_id, ingested_at=ingested_at, **bureau,
        )
        summary["nodes_written"].append("BureauProfile:1")
        summary["relationships_written"].append("HAS_BUREAU_PROFILE:1")
    else:
        summary["skipped"].append("bureau missing/invalid")

    financials = (source_jsons.get("financials") or {}).get("data")
    if financials:
        snapshot_id = f"{case_id}:financials:{financials['period']}"
        run_write(
            """
            MERGE (f:FinancialsSnapshot {snapshot_id: $snapshot_id})
            SET f.period = $period,
                f.is_audited = $is_audited,
                f.revenue = $revenue,
                f.ebitda = $ebitda,
                f.net_profit = $net_profit,
                f.total_assets = $total_assets,
                f.total_liabilities = $total_liabilities,
                f.net_worth = $net_worth,
                f.debt_equity_ratio = $debt_equity_ratio,
                f.case_id = $case_id,
                f.ingested_at = $ingested_at
            WITH f
            MATCH (c:Company {cin: $cin})
            MERGE (c)-[:REPORTED_FINANCIALS]->(f)
            """,
            snapshot_id=snapshot_id, cin=cin, case_id=case_id, ingested_at=ingested_at, **financials,
        )
        summary["nodes_written"].append("FinancialsSnapshot:1")
        summary["relationships_written"].append("REPORTED_FINANCIALS:1")
    else:
        summary["skipped"].append("financials missing/invalid")

    ledger = (source_jsons.get("ledger") or {}).get("data")
    if ledger:
        snapshot_id = f"{case_id}:ledger:{ledger['period']}"
        run_write(
            """
            MERGE (l:LedgerSnapshot {snapshot_id: $snapshot_id})
            SET l.period = $period,
                l.total_sales = $total_sales,
                l.total_purchases = $total_purchases,
                l.debtor_days = $debtor_days,
                l.creditor_days = $creditor_days,
                l.top_debtor_concentration_pct = $top_debtor_concentration_pct,
                l.overdue_receivables = $overdue_receivables,
                l.case_id = $case_id,
                l.ingested_at = $ingested_at
            WITH l
            MATCH (c:Company {cin: $cin})
            MERGE (c)-[:REPORTED_LEDGER]->(l)
            """,
            snapshot_id=snapshot_id, cin=cin, case_id=case_id, ingested_at=ingested_at, **ledger,
        )
        summary["nodes_written"].append("LedgerSnapshot:1")
        summary["relationships_written"].append("REPORTED_LEDGER:1")
    else:
        summary["skipped"].append("ledger missing/invalid")

    return summary
