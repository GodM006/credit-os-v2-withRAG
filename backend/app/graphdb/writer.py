"""
Takes Layer 1's `source_jsons` for a case and projects it into the Neo4j
context graph.

Node types written:
  Hop-0: Company
  Hop-1: Director, GSTEntity, BankAccount, BureauProfile, FinancialsSnapshot, LedgerSnapshot
  Hop-2: Counterparty (from LedgerSnapshot and BankAccount),
          LoanFacility (from BureauProfile),
          PersonalBureauProfile (from Director)

Relationships:
  HAS_DIRECTOR, FILED_GST, HOLDS_ACCOUNT, HAS_BUREAU_PROFILE,
  REPORTED_FINANCIALS, REPORTED_LEDGER, HAS_COUNTERPARTY, HAS_FACILITY,
  HAS_PERSONAL_BUREAU, RELATED_COMPANY

`data_availability` in the returned summary dict records per-branch
availability so the frontend can show a coverage panel without relying
on placeholder nodes. No node is ever written with fake/zero data just
to keep the graph "complete"-looking.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict

from app.graphdb.neo4j_client import run_write


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_name(name: str) -> str:
    """Lowercase, strip punctuation/diacritics, collapse whitespace — used as entity-resolution key."""
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-z0-9 ]", "", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def write_case_to_graph(case_id: str, source_jsons: Dict[str, Any]) -> Dict[str, Any]:
    summary = {
        "nodes_written": [],
        "relationships_written": [],
        "skipped": [],          # kept for backward compat (list of human-readable strings)
        "data_availability": {},  # structured: {branch_key: {available, reason, count}}
        "company_cin": None,
    }
    ingested_at = _now()

    # ── Company (anchor) ──────────────────────────────────────────────────────
    kyc = (source_jsons.get("kyc") or {}).get("data")
    if not kyc:
        summary["skipped"].append("kyc missing/invalid - cannot anchor a Company node without a CIN")
        return summary

    cin = (kyc.get("cin") or "").strip()
    if not cin:
        fallback = (kyc.get("pan") or "").strip() or (kyc.get("legal_name") or "").strip() or f"CASE_{case_id}"
        cin = fallback
        summary["skipped"].append(f"kyc.cin is empty (non-corporate entity) - fell back to '{cin}' as anchor identifier")
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
        legal_name=kyc.get("legal_name", ""),
        pan=kyc.get("pan", ""),
        incorporation_date=str(kyc.get("incorporation_date", "") or ""),
        entity_type=kyc.get("entity_type", ""),
        registered_address=kyc.get("registered_address", ""),
        kyc_doc_status=kyc.get("kyc_doc_status", ""),
        case_id=case_id,
        ingested_at=ingested_at,
    )
    summary["nodes_written"].append("Company:1")

    # ── Directors + Phase 2: RELATED_COMPANY edges ───────────────────────────
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
        # Phase 2: materialize RELATED_COMPANY edge if this Director is already
        # on another Company in the graph (from a prior case).
        run_write(
            """
            MATCH (c:Company {cin: $cin})-[:HAS_DIRECTOR]->(d:Director {din: $din})<-[:HAS_DIRECTOR]-(other:Company)
            WHERE other.cin <> $cin
            MERGE (c)-[:RELATED_COMPANY {via_director: $din}]->(other)
            """,
            cin=cin, din=director["din"],
        )
    if directors:
        summary["nodes_written"].append(f"Director:{len(directors)}")
        summary["relationships_written"].append(f"HAS_DIRECTOR:{len(directors)}")

    # ── GSTEntity ─────────────────────────────────────────────────────────────
    gst = (source_jsons.get("gst") or {}).get("data")
    if gst and gst.get("gstin"):
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
            cin=cin,
            case_id=case_id,
            ingested_at=ingested_at,
            gstin=gst.get("gstin"),
            legal_name=gst.get("legal_name"),
            registration_date=str(gst.get("registration_date") or "") if gst.get("registration_date") else None,
            filing_frequency=gst.get("filing_frequency"),
            filing_status=gst.get("filing_status"),
            last_filed_period=gst.get("last_filed_period"),
            gstr3b_annual_turnover=float(gst.get("gstr3b_annual_turnover") or 0) if gst.get("gstr3b_annual_turnover") is not None else None,
            gstr1_annual_turnover=float(gst.get("gstr1_annual_turnover") or 0) if gst.get("gstr1_annual_turnover") is not None else None,
            vintage_months=int(gst.get("vintage_months") or 0) if gst.get("vintage_months") is not None else None,
            late_filings_last_12m=int(gst.get("late_filings_last_12m") or 0) if gst.get("late_filings_last_12m") is not None else None,
        )
        summary["nodes_written"].append("GSTEntity:1")
        summary["relationships_written"].append("FILED_GST:1")
    else:
        summary["skipped"].append("gst missing/invalid or gstin is null")

    # ── BankAccount + Phase 3: Counterparty nodes ────────────────────────────
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
                statement_period_start=str(banking.get("statement_period_start", "") or ""),
                statement_period_end=str(banking.get("statement_period_end", "") or ""),
                total_credits=float(banking.get("total_credits") or 0),
                total_debits=float(banking.get("total_debits") or 0),
                avg_monthly_balance=float(banking.get("avg_monthly_balance") or 0),
                min_balance=float(banking.get("min_balance") or 0),
                bounce_count=int(banking.get("bounce_count") or 0),
                inferred_annual_turnover=float(banking.get("inferred_annual_turnover") or 0),
                cash_deposit_ratio=banking.get("cash_deposit_ratio"),
                case_id=case_id,
                ingested_at=ingested_at,
                cin=cin,
            )

        # Phase 3: bank counterparties (best-effort, keyed on normalized_name:case_id)
        bank_counterparties = banking.get("top_counterparties") or []
        cp_written = 0
        for cp in bank_counterparties:
            cp_name = cp.get("name") or ""
            if not cp_name.strip():
                continue
            norm_name = _normalize_name(cp_name)
            cp_id = f"{case_id}:bank_cp:{norm_name}:{cp.get('direction', 'inflow')}"
            run_write(
                """
                MERGE (cp:Counterparty {counterparty_id: $counterparty_id})
                SET cp.name = $name,
                    cp.source = 'bank',
                    cp.direction = $direction,
                    cp.total_amount = $total_amount,
                    cp.transaction_count = $transaction_count,
                    cp.confidence = $confidence,
                    cp.case_id = $case_id,
                    cp.ingested_at = $ingested_at
                WITH cp
                MATCH (b:BankAccount {account_key: $account_key})
                MERGE (b)-[:HAS_COUNTERPARTY {direction: $direction}]->(cp)
                """,
                counterparty_id=cp_id,
                name=cp_name,
                direction=cp.get("direction", "inflow"),
                total_amount=float(cp.get("total_amount") or 0),
                transaction_count=int(cp.get("transaction_count") or 0),
                confidence=cp.get("confidence", "low"),
                case_id=case_id,
                ingested_at=ingested_at,
                # use first account key for the edge — bank counterparties span the whole statement
                account_key=f"{accounts[0]['bank_name']}:{accounts[0]['account_number_masked']}",
            )
            cp_written += 1

        summary["nodes_written"].append(f"BankAccount:{len(accounts)}")
        summary["relationships_written"].append(f"HOLDS_ACCOUNT:{len(accounts)}")
        if cp_written:
            summary["nodes_written"].append(f"Counterparty(bank):{cp_written}")
            summary["relationships_written"].append(f"HAS_COUNTERPARTY(bank):{cp_written}")
        summary["data_availability"]["bank_counterparties"] = {
            "available": cp_written > 0,
            "count": cp_written,
            "reason": "no identifiable counterparties in narrations" if cp_written == 0 else None,
        }

        # Phase 4: BankRiskEvent nodes off BankAccount
        risk_events = banking.get("risk_events") or []
        re_written = 0
        first_acc_key = f"{accounts[0]['bank_name']}:{accounts[0]['account_number_masked']}"
        for idx, re_item in enumerate(risk_events):
            etype = re_item.get("event_type") or "nach_ecs_bounce"
            event_id = f"{case_id}:{first_acc_key}:event:{idx}"
            run_write(
                """
                MERGE (re:BankRiskEvent {event_id: $event_id})
                SET re.event_type = $event_type,
                    re.event_date = $event_date,
                    re.amount = $amount,
                    re.narration_snippet = $narration_snippet,
                    re.confidence = $confidence,
                    re.case_id = $case_id,
                    re.ingested_at = $ingested_at
                WITH re
                MATCH (b:BankAccount {account_key: $account_key})
                MERGE (b)-[:HAS_RISK_EVENT]->(re)
                """,
                event_id=event_id,
                event_type=etype,
                event_date=re_item.get("event_date") or "",
                amount=float(re_item.get("amount") or 0),
                narration_snippet=re_item.get("narration_snippet") or "",
                confidence=re_item.get("confidence") or "low",
                case_id=case_id,
                ingested_at=ingested_at,
                account_key=first_acc_key,
            )
            re_written += 1

        if re_written:
            summary["nodes_written"].append(f"BankRiskEvent:{re_written}")
            summary["relationships_written"].append(f"HAS_RISK_EVENT:{re_written}")
        summary["data_availability"]["bank_risk_events"] = {
            "available": re_written > 0,
            "count": re_written,
            "reason": "no risk events flagged in bank statement narrations" if re_written == 0 else None,
        }
    else:
        summary["skipped"].append("banking missing/invalid")
        summary["data_availability"]["bank_counterparties"] = {
            "available": False,
            "reason": "bank statement not uploaded or failed extraction",
        }
        summary["data_availability"]["bank_risk_events"] = {
            "available": False,
            "reason": "bank statement not uploaded or failed extraction",
        }


    # ── BureauProfile + Phase 4: LoanFacility + PersonalBureauProfile ────────
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
            profile_id=profile_id,
            cin=cin,
            case_id=case_id,
            ingested_at=ingested_at,
            entity_type=bureau.get("entity_type") or "",
            bureau_score=bureau.get("bureau_score"),
            total_exposure=float(bureau.get("total_exposure") or 0),
            overdue_amount=float(bureau.get("overdue_amount") or 0),
            dpd_30=int(bureau.get("dpd_30") or 0),
            dpd_60=int(bureau.get("dpd_60") or 0),
            dpd_90_plus=int(bureau.get("dpd_90_plus") or 0),
            enquiries_last_6m=int(bureau.get("enquiries_last_6m") or 0),
            written_off_accounts=int(bureau.get("written_off_accounts") or 0),
            active_accounts=int(bureau.get("active_accounts") or 0),
        )
        summary["nodes_written"].append("BureauProfile:1")
        summary["relationships_written"].append("HAS_BUREAU_PROFILE:1")

        # Build director lookup for matching guarantors and personal CIR entries
        director_lookup = {}
        for d in directors:
            norm = _normalize_name(d.get("name", ""))
            if norm:
                director_lookup[norm] = d.get("din", "")

        # Phase 4a & Phase 6: LoanFacility nodes + GUARANTEED_BY edges
        facilities = bureau.get("facilities") or []
        fac_written = 0
        guar_written = 0
        for i, fac in enumerate(facilities):
            lender = fac.get("lender_name") or ""
            if not lender.strip() and not fac.get("facility_type", "").strip():
                continue  # skip empty rows
            facility_id = f"{case_id}:facility:{i}"
            guarantor = fac.get("guarantor_name") or ""
            run_write(
                """
                MERGE (f:LoanFacility {facility_id: $facility_id})
                SET f.lender_name = $lender_name,
                    f.facility_type = $facility_type,
                    f.sanctioned_amount = $sanctioned_amount,
                    f.outstanding_amount = $outstanding_amount,
                    f.dpd_bucket = $dpd_bucket,
                    f.account_status = $account_status,
                    f.guarantor_name = $guarantor_name,
                    f.case_id = $case_id,
                    f.ingested_at = $ingested_at
                WITH f
                MATCH (p:BureauProfile {profile_id: $profile_id})
                MERGE (p)-[:HAS_FACILITY]->(f)
                """,
                facility_id=facility_id,
                profile_id=profile_id,
                lender_name=lender,
                facility_type=fac.get("facility_type") or "",
                sanctioned_amount=float(fac.get("sanctioned_amount") or 0),
                outstanding_amount=float(fac.get("outstanding_amount") or 0),
                dpd_bucket=str(fac.get("dpd_bucket") or "0"),
                account_status=fac.get("account_status") or "",
                guarantor_name=guarantor,
                case_id=case_id,
                ingested_at=ingested_at,
            )
            fac_written += 1

            if guarantor.strip():
                matched_din = director_lookup.get(_normalize_name(guarantor))
                if matched_din:
                    run_write(
                        """
                        MATCH (f:LoanFacility {facility_id: $facility_id})
                        MATCH (d:Director {din: $din})
                        MERGE (f)-[:GUARANTEED_BY]->(d)
                        """,
                        facility_id=facility_id,
                        din=matched_din,
                    )
                    guar_written += 1

        if fac_written:
            summary["nodes_written"].append(f"LoanFacility:{fac_written}")
            summary["relationships_written"].append(f"HAS_FACILITY:{fac_written}")
        if guar_written:
            summary["relationships_written"].append(f"GUARANTEED_BY:{guar_written}")
        summary["data_availability"]["loan_facilities"] = {
            "available": fac_written > 0,
            "count": fac_written,
            "guaranteed_count": guar_written,
            "reason": "no itemized facility table found in bureau document" if fac_written == 0 else None,
        }


        # Phase 2a: Commercial CreditEnquiry nodes
        commercial_enquiries = bureau.get("enquiries") or []
        enq_written = 0
        for i, enq in enumerate(commercial_enquiries):
            lender = enq.get("lender_name") or ""
            if not lender.strip() and not enq.get("enquiry_date", "").strip():
                continue
            enq_id = f"{profile_id}:enquiry:{i}"
            run_write(
                """
                MERGE (ce:CreditEnquiry {enquiry_id: $enquiry_id})
                SET ce.lender_name = $lender_name,
                    ce.enquiry_date = $enquiry_date,
                    ce.purpose = $purpose,
                    ce.amount = $amount,
                    ce.is_personal = false,
                    ce.case_id = $case_id,
                    ce.ingested_at = $ingested_at
                WITH ce
                MATCH (p:BureauProfile {profile_id: $profile_id})
                MERGE (p)-[:HAS_ENQUIRY]->(ce)
                """,
                enquiry_id=enq_id,
                profile_id=profile_id,
                lender_name=lender,
                enquiry_date=enq.get("enquiry_date") or "",
                purpose=enq.get("purpose") or "",
                amount=float(enq.get("amount") or 0),
                case_id=case_id,
                ingested_at=ingested_at,
            )
            enq_written += 1

        if enq_written:
            summary["nodes_written"].append(f"CreditEnquiry(commercial):{enq_written}")
            summary["relationships_written"].append(f"HAS_ENQUIRY(commercial):{enq_written}")
        summary["data_availability"]["commercial_enquiries"] = {
            "available": enq_written > 0,
            "count": enq_written,
            "reason": "no itemized enquiry section found in commercial bureau report" if enq_written == 0 else None,
        }


        # Phase 4b: PersonalBureauProfile nodes — match each entry to a Director by PAN or name
        personal_entries = bureau.get("personal_entries") or []
        personal_written = 0
        personal_fac_written = 0
        personal_enq_written = 0
        # Build lookup: normalize director names and PANs for matching


        director_lookup = {}
        for d in directors:
            norm = _normalize_name(d.get("name", ""))
            director_lookup[norm] = d.get("din", "")

        for j, entry in enumerate(personal_entries):
            entry_name = entry.get("director_name") or ""
            entry_pan = (entry.get("director_pan") or "").strip().upper()
            if not entry_name.strip():
                continue

            # Try to find the matching Director DIN
            matched_din = None
            if entry_pan:
                # PAN match: query Director nodes for this PAN (more reliable)
                pan_rows = run_write(
                    "MATCH (d:Director) WHERE d.pan = $pan RETURN d.din AS din LIMIT 1",
                    pan=entry_pan,
                )
                if pan_rows:
                    matched_din = pan_rows[0].get("din")

            if not matched_din:
                # Name similarity: use normalized name key lookup
                norm_entry = _normalize_name(entry_name)
                matched_din = director_lookup.get(norm_entry)
                if not matched_din:
                    # Partial match: any director name that contains the entry name as a substring
                    for norm_dir_name, din in director_lookup.items():
                        if norm_entry and (norm_entry in norm_dir_name or norm_dir_name in norm_entry):
                            matched_din = din
                            break

            if not matched_din:
                summary["skipped"].append(
                    f"PersonalBureauEntry for '{entry_name}' could not be matched to any Director — no DIN match by PAN or name"
                )
                continue

            pb_id = f"{case_id}:personal_bureau:{j}"
            run_write(
                """
                MERGE (pb:PersonalBureauProfile {personal_bureau_id: $pb_id})
                SET pb.director_name = $director_name,
                    pb.director_pan = $director_pan,
                    pb.bureau_score = $bureau_score,
                    pb.total_exposure = $total_exposure,
                    pb.overdue_amount = $overdue_amount,
                    pb.dpd_30 = $dpd_30,
                    pb.dpd_60 = $dpd_60,
                    pb.dpd_90_plus = $dpd_90_plus,
                    pb.enquiries_last_6m = $enquiries_last_6m,
                    pb.written_off_accounts = $written_off_accounts,
                    pb.active_accounts = $active_accounts,
                    pb.case_id = $case_id,
                    pb.ingested_at = $ingested_at
                WITH pb
                MATCH (d:Director {din: $din})
                MERGE (d)-[:HAS_PERSONAL_BUREAU]->(pb)
                """,
                pb_id=pb_id,
                din=matched_din,
                director_name=entry_name,
                director_pan=entry_pan or None,
                bureau_score=entry.get("bureau_score"),
                total_exposure=float(entry.get("total_exposure") or 0),
                overdue_amount=float(entry.get("overdue_amount") or 0),
                dpd_30=int(entry.get("dpd_30") or 0),
                dpd_60=int(entry.get("dpd_60") or 0),
                dpd_90_plus=int(entry.get("dpd_90_plus") or 0),
                enquiries_last_6m=int(entry.get("enquiries_last_6m") or 0),
                written_off_accounts=int(entry.get("written_off_accounts") or 0),
                active_accounts=int(entry.get("active_accounts") or 0),
                case_id=case_id,
                ingested_at=ingested_at,
            )
            personal_written += 1

            # Phase 1: PersonalLoanFacility nodes under this PersonalBureauProfile
            p_facilities = entry.get("facilities") or []
            for k, pfac in enumerate(p_facilities):
                plender = pfac.get("lender_name") or ""
                if not plender.strip() and not pfac.get("facility_type", "").strip():
                    continue
                pfac_id = f"{pb_id}:facility:{k}"
                pguarantor = pfac.get("guarantor_name") or ""
                run_write(
                    """
                    MERGE (f:LoanFacility {facility_id: $facility_id})
                    SET f.lender_name = $lender_name,
                        f.facility_type = $facility_type,
                        f.sanctioned_amount = $sanctioned_amount,
                        f.outstanding_amount = $outstanding_amount,
                        f.dpd_bucket = $dpd_bucket,
                        f.account_status = $account_status,
                        f.guarantor_name = $guarantor_name,
                        f.is_personal = true,
                        f.case_id = $case_id,
                        f.ingested_at = $ingested_at
                    WITH f
                    MATCH (pb:PersonalBureauProfile {personal_bureau_id: $pb_id})
                    MERGE (pb)-[:HAS_FACILITY]->(f)
                    """,
                    facility_id=pfac_id,
                    pb_id=pb_id,
                    lender_name=plender,
                    facility_type=pfac.get("facility_type") or "",
                    sanctioned_amount=float(pfac.get("sanctioned_amount") or 0),
                    outstanding_amount=float(pfac.get("outstanding_amount") or 0),
                    dpd_bucket=str(pfac.get("dpd_bucket") or "0"),
                    account_status=pfac.get("account_status") or "",
                    guarantor_name=pguarantor,
                    case_id=case_id,
                    ingested_at=ingested_at,
                )
                personal_fac_written += 1

                if pguarantor.strip():
                    p_matched_din = director_lookup.get(_normalize_name(pguarantor))
                    if p_matched_din:
                        run_write(
                            """
                            MATCH (f:LoanFacility {facility_id: $facility_id})
                            MATCH (d:Director {din: $din})
                            MERGE (f)-[:GUARANTEED_BY]->(d)
                            """,
                            facility_id=pfac_id,
                            din=p_matched_din,
                        )
                        guar_written += 1


            # Phase 2b: Personal CreditEnquiry nodes under this PersonalBureauProfile
            p_enquiries = entry.get("enquiries") or []
            for k, penq in enumerate(p_enquiries):
                plender = penq.get("lender_name") or ""
                if not plender.strip() and not penq.get("enquiry_date", "").strip():
                    continue
                penq_id = f"{pb_id}:enquiry:{k}"
                run_write(
                    """
                    MERGE (ce:CreditEnquiry {enquiry_id: $enquiry_id})
                    SET ce.lender_name = $lender_name,
                        ce.enquiry_date = $enquiry_date,
                        ce.purpose = $purpose,
                        ce.amount = $amount,
                        ce.is_personal = true,
                        ce.case_id = $case_id,
                        ce.ingested_at = $ingested_at
                    WITH ce
                    MATCH (pb:PersonalBureauProfile {personal_bureau_id: $pb_id})
                    MERGE (pb)-[:HAS_ENQUIRY]->(ce)
                    """,
                    enquiry_id=penq_id,
                    pb_id=pb_id,
                    lender_name=plender,
                    enquiry_date=penq.get("enquiry_date") or "",
                    purpose=penq.get("purpose") or "",
                    amount=float(penq.get("amount") or 0),
                    case_id=case_id,
                    ingested_at=ingested_at,
                )
                personal_enq_written += 1

        if personal_written:
            summary["nodes_written"].append(f"PersonalBureauProfile:{personal_written}")
            summary["relationships_written"].append(f"HAS_PERSONAL_BUREAU:{personal_written}")
        if personal_fac_written:
            summary["nodes_written"].append(f"LoanFacility(personal):{personal_fac_written}")
            summary["relationships_written"].append(f"HAS_FACILITY(personal):{personal_fac_written}")
        if personal_enq_written:
            summary["nodes_written"].append(f"CreditEnquiry(personal):{personal_enq_written}")
            summary["relationships_written"].append(f"HAS_ENQUIRY(personal):{personal_enq_written}")
        summary["data_availability"]["personal_bureau"] = {
            "available": personal_written > 0,
            "count": personal_written,
            "facilities_count": personal_fac_written,
            "enquiries_count": personal_enq_written,
            "reason": (
                "no personal CIR found in bureau document" if not personal_entries
                else "personal CIR present but could not be matched to any Director by name or PAN"
            ) if personal_written == 0 else None,
        }



    else:
        summary["skipped"].append("bureau missing/invalid")
        summary["data_availability"]["loan_facilities"] = {
            "available": False,
            "reason": "bureau document not uploaded or failed extraction",
        }
        summary["data_availability"]["personal_bureau"] = {
            "available": False,
            "reason": "bureau document not uploaded or failed extraction",
        }

    # ── FinancialsSnapshot ────────────────────────────────────────────────────
    financials = (source_jsons.get("financials") or {}).get("data")
    if financials:
        snapshot_id = f"{case_id}:financials:{financials.get('period', 'unknown')}"
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
            snapshot_id=snapshot_id,
            cin=cin,
            case_id=case_id,
            ingested_at=ingested_at,
            period=str(financials.get("period", "") or ""),
            is_audited=bool(financials.get("is_audited")),
            revenue=float(financials.get("revenue") or 0),
            ebitda=float(financials.get("ebitda") or 0),
            net_profit=float(financials.get("net_profit") or 0),
            total_assets=float(financials.get("total_assets") or 0),
            total_liabilities=float(financials.get("total_liabilities") or 0),
            net_worth=float(financials.get("net_worth") or 0),
            debt_equity_ratio=float(financials.get("debt_equity_ratio") or 0),
        )
        summary["nodes_written"].append("FinancialsSnapshot:1")
        summary["relationships_written"].append("REPORTED_FINANCIALS:1")
    else:
        summary["skipped"].append("financials missing/invalid")

    # ── LedgerSnapshot + Phase 1: Counterparty nodes ─────────────────────────
    ledger = (source_jsons.get("ledger") or {}).get("data")
    if ledger:
        snapshot_id = f"{case_id}:ledger:{ledger.get('period', 'unknown')}"
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
            snapshot_id=snapshot_id,
            cin=cin,
            case_id=case_id,
            ingested_at=ingested_at,
            period=str(ledger.get("period", "") or ""),
            total_sales=float(ledger.get("total_sales") or 0),
            total_purchases=float(ledger.get("total_purchases") or 0),
            debtor_days=float(ledger.get("debtor_days") or 0),
            creditor_days=float(ledger.get("creditor_days") or 0),
            top_debtor_concentration_pct=float(ledger.get("top_debtor_concentration_pct") or 0),
            overdue_receivables=float(ledger.get("overdue_receivables") or 0),
        )
        summary["nodes_written"].append("LedgerSnapshot:1")
        summary["relationships_written"].append("REPORTED_LEDGER:1")

        # Phase 1: write Counterparty nodes for named debtors and creditors
        all_counterparties = list(ledger.get("top_debtors") or []) + list(ledger.get("top_creditors") or [])
        ledger_cp_written = 0
        for cp in all_counterparties:
            cp_name = cp.get("name") or ""
            if not cp_name.strip():
                continue
            cp_gstin = (cp.get("gstin") or "").strip() or None
            norm_name = _normalize_name(cp_name)
            # Key: GSTIN wins if available (cross-case deduplication); else normalized name within case
            cp_key = cp_gstin if cp_gstin else f"{case_id}:{norm_name}"
            cp_id = f"ledger:{cp_key}:{cp.get('role', 'debtor')}"
            run_write(
                """
                MERGE (cp:Counterparty {counterparty_id: $counterparty_id})
                SET cp.name = $name,
                    cp.gstin = $gstin,
                    cp.role = $role,
                    cp.source = 'ledger',
                    cp.total_invoice_value = $total_invoice_value,
                    cp.pct_of_total = $pct_of_total,
                    cp.case_id = $case_id,
                    cp.ingested_at = $ingested_at
                WITH cp
                MATCH (l:LedgerSnapshot {snapshot_id: $snapshot_id})
                MERGE (l)-[:HAS_COUNTERPARTY {role: $role}]->(cp)
                """,
                counterparty_id=cp_id,
                name=cp_name,
                gstin=cp_gstin,
                role=cp.get("role", "debtor"),
                total_invoice_value=float(cp.get("total_invoice_value") or 0),
                pct_of_total=float(cp.get("pct_of_total") or 0) if cp.get("pct_of_total") is not None else None,
                case_id=case_id,
                ingested_at=ingested_at,
                snapshot_id=snapshot_id,
            )
            ledger_cp_written += 1

        if ledger_cp_written:
            summary["nodes_written"].append(f"Counterparty(ledger):{ledger_cp_written}")
            summary["relationships_written"].append(f"HAS_COUNTERPARTY(ledger):{ledger_cp_written}")
        summary["data_availability"]["ledger_counterparties"] = {
            "available": ledger_cp_written > 0,
            "count": ledger_cp_written,
            "reason": "no named buyers/suppliers found in ledger" if ledger_cp_written == 0 else None,
        }
    else:
        summary["skipped"].append("ledger missing/invalid")
        summary["data_availability"]["ledger_counterparties"] = {
            "available": False,
            "reason": "ledger document not uploaded or failed extraction",
        }

    # ── Phase 5: Counterparty ↔ GSTEntity entity resolution ──────────────────
    # For every Counterparty node written for this case that carries a GSTIN,
    # check whether that GSTIN matches an existing GSTEntity in the graph.
    # If it does, MERGE a POSSIBLE_SAME_ENTITY_AS edge (corroboration only —
    # the two nodes are never merged/collapsed).
    # GSTIN equality is the only match criterion; no fuzzy name matching here.
    cp_resolved = 0
    try:
        resolved_rows = run_write(
            """
            MATCH (cp:Counterparty {case_id: $case_id})
            WHERE cp.gstin IS NOT NULL AND cp.gstin <> ''
            WITH cp
            MATCH (g:GSTEntity {gstin: cp.gstin})
            MERGE (cp)-[m:POSSIBLE_SAME_ENTITY_AS]->(g)
            ON CREATE SET m.matched_at = $matched_at
            RETURN count(m) AS resolved
            """,
            case_id=case_id,
            matched_at=ingested_at,
        )
        if resolved_rows:
            cp_resolved = resolved_rows[0].get("resolved", 0) or 0
    except Exception as e:
        summary["skipped"].append(f"Counterparty→GSTEntity resolution failed: {e}")

    summary["data_availability"]["counterparty_entity_resolution"] = {
        "available": cp_resolved > 0,
        "count": int(cp_resolved),
        "reason": "no counterparties with GSTIN matched an existing GSTEntity" if cp_resolved == 0 else None,
    }
    if cp_resolved:
        summary["relationships_written"].append(f"POSSIBLE_SAME_ENTITY_AS:{cp_resolved}")

    return summary
