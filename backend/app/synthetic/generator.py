"""
Generates synthetic "raw documents" for a fictitious SME loan applicant -
one free-text blob per Layer 1 source. These stand in for OCR'd bank
statements, GST filings, bureau reports, etc.

Three scenarios:
  - clean        : numbers are internally consistent, applicant looks healthy
  - noisy        : messy formatting (like real OCR output) but no real red flags
  - fraud_risk    : internally consistent formatting, but seeded with red flags
                    (turnover mismatch, high cash deposits, DPD, anchor
                    concentration) for Layer 3's triangulation engine to catch later

This is deliberately NOT using an LLM - it's plain Python so it's fast,
free, and deterministic enough to regenerate edge cases on demand.
"""
from __future__ import annotations

import random
import uuid
from datetime import date, timedelta
from typing import Literal

Scenario = Literal["clean", "noisy", "fraud_risk"]

COMPANY_NAMES = [
    "Vortex Engineering Pvt Ltd", "Meridian Textiles Pvt Ltd", "Brightedge Polymers Pvt Ltd",
    "Northbridge Components LLP", "Saffron Foods Pvt Ltd", "Quantel Electronics Pvt Ltd",
]
DIRECTOR_NAMES = ["Rohan Mehta", "Anjali Sharma", "Vikram Iyer", "Priya Nair", "Suresh Reddy", "Kavita Joshi"]
BANKS = ["HDFC Bank", "ICICI Bank", "Axis Bank", "State Bank of India", "Kotak Mahindra Bank"]


def _gstin(state_code: str = "27") -> str:
    pan_part = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=5)) + "".join(
        random.choices("0123456789", k=4)
    ) + random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    return f"{state_code}{pan_part}1Z{random.choice('0123456789')}"


def _pan() -> str:
    return "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=5)) + "".join(
        random.choices("0123456789", k=4)
    ) + random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")


def _cin() -> str:
    return f"U{random.randint(10000,99999)}MH{random.randint(2008,2022)}PTC{random.randint(100000,999999)}"


def generate_case(
    scenario: Scenario = "clean",
    force_director: tuple[str, str] | None = None,
    force_bank_account: tuple[str, str] | None = None,
) -> dict:
    company = random.choice(COMPANY_NAMES)
    today = date(2026, 3, 31)
    incorp_date = today - timedelta(days=random.randint(3 * 365, 12 * 365))
    vintage_months = max(12, (today - incorp_date).days // 30)

    base_turnover = random.randint(15_000_000, 60_000_000)  # INR 1.5Cr - 6Cr
    bank_turnover = base_turnover
    gst_turnover_3b = base_turnover
    gst_turnover_1 = base_turnover
    cash_ratio = round(random.uniform(0.02, 0.08), 2)
    bounce_count = random.randint(0, 1)
    bureau_score = random.randint(740, 820)
    dpd90 = 0
    written_off = 0
    debtor_conc = round(random.uniform(15, 35), 1)
    filing_status = "regular"
    is_audited = True
    debt_equity = round(random.uniform(0.4, 1.2), 2)

    if scenario == "fraud_risk":
        gst_turnover_3b = int(base_turnover * random.uniform(0.55, 0.7))  # bank shows much more than GST
        cash_ratio = round(random.uniform(0.35, 0.55), 2)
        bounce_count = random.randint(3, 7)
        bureau_score = random.randint(580, 650)
        dpd90 = random.randint(1, 3)
        debtor_conc = round(random.uniform(72, 90), 1)
        filing_status = random.choice(["defaulter", "suspended"])
        is_audited = False
        debt_equity = round(random.uniform(3.2, 5.0), 2)

    accounts = [(random.choice(BANKS), random.choice(["current", "current", "cc_od"])) for _ in range(random.randint(1, 2))]
    account_numbers = [str(random.randint(1000, 9999)) for _ in accounts]
    if force_bank_account:
        accounts[0] = (force_bank_account[0], "current")
        account_numbers[0] = force_bank_account[1]
    avg_balance = int(bank_turnover * random.uniform(0.04, 0.08))
    min_balance = int(avg_balance * random.uniform(0.1, 0.4))

    directors = random.sample(DIRECTOR_NAMES, k=random.randint(2, 3))
    director_records = [(n, str(random.randint(1000000, 9999999))) for n in directors]
    if force_director:
        director_records[0] = force_director
    gstin = _gstin()
    pan = _pan()
    cin = _cin()

    period_start = date(2025, 4, 1)
    period_end = date(2026, 3, 31)

    banking_doc = (
        f"BANK STATEMENT SUMMARY\n"
        f"Account Holder: {company}\n"
        f"Statement Period: {period_start.strftime('%d-%b-%Y')} to {period_end.strftime('%d-%b-%Y')}\n"
        f"Accounts: " + "; ".join(f"{b} ({t.upper()}) A/c ending {num}" for (b, t), num in zip(accounts, account_numbers)) + "\n"
        f"Total Credits: INR {bank_turnover:,}\n"
        f"Total Debits: INR {int(bank_turnover * random.uniform(0.85, 0.97)):,}\n"
        f"Average Monthly Balance: INR {avg_balance:,}\n"
        f"Minimum Balance Observed: INR {min_balance:,}\n"
        f"Cheque/ECS Returns (12m): {bounce_count}\n"
        f"Cash Deposits as % of Credits: {int(cash_ratio*100)}%\n"
    )

    gst_doc = (
        f"GST PROFILE & RETURN SUMMARY\n"
        f"GSTIN: {gstin}\n"
        f"Legal Name: {company}\n"
        f"Date of Registration: {incorp_date.strftime('%d-%b-%Y')}\n"
        f"Filing Frequency: Monthly\n"
        f"Filing Status: {filing_status.upper()}\n"
        f"Last Filed Period: Feb-2026\n"
        f"GSTR-3B Reported Annual Turnover: INR {gst_turnover_3b:,}\n"
        f"GSTR-1 Reported Annual Turnover: INR {gst_turnover_1:,}\n"
        f"Late Filings (last 12 months): {random.randint(0,1) if scenario!='fraud_risk' else random.randint(2,5)}\n"
    )

    bureau_doc = (
        f"COMMERCIAL CREDIT BUREAU REPORT\n"
        f"Entity: {company}\n"
        f"Bureau Score: {bureau_score}\n"
        f"Total Exposure Across Lenders: INR {int(bank_turnover*0.15):,}\n"
        f"Overdue Amount: INR {0 if dpd90==0 else int(bank_turnover*0.02):,}\n"
        f"Accounts 30 DPD: {random.randint(0,1) if scenario!='fraud_risk' else random.randint(1,3)}\n"
        f"Accounts 60 DPD: {0 if scenario!='fraud_risk' else random.randint(0,2)}\n"
        f"Accounts 90+ DPD: {dpd90}\n"
        f"Hard Enquiries (last 6 months): {random.randint(1,3) if scenario!='fraud_risk' else random.randint(4,8)}\n"
        f"Written-off Accounts: {written_off}\n"
        f"Active Accounts: {random.randint(2,5)}\n"
    )

    revenue = gst_turnover_3b
    ebitda = int(revenue * random.uniform(0.10, 0.18))
    net_profit = int(ebitda * random.uniform(0.5, 0.8))
    total_assets = int(revenue * random.uniform(0.6, 1.1))
    total_liabilities = int(total_assets * (debt_equity / (1 + debt_equity)))
    net_worth = total_assets - total_liabilities

    financials_doc = (
        f"FINANCIAL STATEMENTS - FY2025-26\n"
        f"Entity: {company}\n"
        f"Audited: {'Yes' if is_audited else 'No'}\n"
        f"Revenue: INR {revenue:,}\n"
        f"EBITDA: INR {ebitda:,}\n"
        f"Net Profit: INR {net_profit:,}\n"
        f"Total Assets: INR {total_assets:,}\n"
        f"Total Liabilities: INR {total_liabilities:,}\n"
        f"Net Worth: INR {net_worth:,}\n"
        f"Debt/Equity Ratio: {debt_equity}\n"
    )

    ledger_doc = (
        f"SALES & PURCHASE LEDGER SUMMARY - FY2025-26\n"
        f"Entity: {company}\n"
        f"Total Sales: INR {revenue:,}\n"
        f"Total Purchases: INR {int(revenue*0.65):,}\n"
        f"Average Debtor Days: {random.randint(35,55) if scenario!='fraud_risk' else random.randint(90,130)}\n"
        f"Average Creditor Days: {random.randint(30,50)}\n"
        f"Largest Single Debtor Concentration: {debtor_conc}%\n"
        f"Overdue Receivables: INR {int(revenue*0.03):,}\n"
    )

    kyc_doc = (
        f"COMPANY KYC & REGISTRATION RECORD\n"
        f"Legal Name: {company}\n"
        f"CIN: {cin}\n"
        f"PAN: {pan}\n"
        f"Date of Incorporation: {incorp_date.strftime('%d-%b-%Y')}\n"
        f"Entity Type: Private Limited Company\n"
        f"Registered Address: Plot 14, MIDC Industrial Area, Pune, Maharashtra 411019\n"
        f"Directors:\n" + "\n".join(f"  - {n}, DIN {din}, Director" for n, din in director_records) + "\n"
        f"KYC Document Status: {'Complete' if scenario != 'fraud_risk' else random.choice(['Incomplete', 'Pending Verification'])}\n"
    )

    if scenario == "noisy":
        # simulate ragged OCR artifacts: stray whitespace, broken lines, odd casing
        def mess(s: str) -> str:
            lines = s.split("\n")
            out = []
            for ln in lines:
                if random.random() < 0.2 and ln.strip():
                    ln = ln.replace(":", " :  ")
                if random.random() < 0.1:
                    ln = ln.upper()
                out.append(ln)
            return "\n".join(out)

        banking_doc, gst_doc, bureau_doc, financials_doc, ledger_doc, kyc_doc = (
            mess(banking_doc), mess(gst_doc), mess(bureau_doc), mess(financials_doc), mess(ledger_doc), mess(kyc_doc)
        )

    return {
        "case_id": str(uuid.uuid4())[:8],
        "scenario": scenario,
        "company_name": company,
        "raw_docs": {
            "banking": banking_doc,
            "gst": gst_doc,
            "bureau": bureau_doc,
            "financials": financials_doc,
            "ledger": ledger_doc,
            "kyc": kyc_doc,
        },
    }


def generate_linked_pair(scenario: Scenario = "clean", share_bank_account: bool = True) -> tuple[dict, dict]:
    """Generates two independent cases that deliberately share one director
    (same name + DIN) and, by default, the same bank account - so Layer 2's
    related-party query AND Layer 3's shared-banking-instrument fraud signal
    both have something real to find. Useful for demoing/testing without
    waiting for a natural collision (which won't happen with random data)."""
    shared_name = random.choice(DIRECTOR_NAMES)
    shared_din = str(random.randint(1000000, 9999999))
    shared_bank = (random.choice(BANKS), str(random.randint(1000, 9999))) if share_bank_account else None

    case_a = generate_case(scenario=scenario, force_director=(shared_name, shared_din), force_bank_account=shared_bank)
    case_b = generate_case(scenario=scenario, force_director=(shared_name, shared_din), force_bank_account=shared_bank)
    return case_a, case_b
