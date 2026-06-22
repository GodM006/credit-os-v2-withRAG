"""
Lightweight business-rule checks on top of Pydantic's type validation.

The architecture diagram calls for Great Expectations here. We're stubbing
that with plain Python rules for now (same input/output shape: a list of
ValidationIssue) so swapping in a real GE Checkpoint later is a drop-in
replacement -- nothing in the agents or graph needs to change, only the
functions in this file.
"""
from __future__ import annotations

from typing import Callable, Dict

from app.schemas.banking import BankingData
from app.schemas.bureau import BureauData
from app.schemas.common import ValidationIssue
from app.schemas.financials import FinancialsData
from app.schemas.gst import GSTData
from app.schemas.kyc import KYCData
from app.schemas.ledger import LedgerData


def status_from_issues(issues: list[ValidationIssue]) -> str:
    if any(i.severity == "error" for i in issues):
        return "invalid"
    if any(i.severity == "warning" for i in issues):
        return "valid_with_warnings"
    return "valid"


def check_banking(d: BankingData) -> list[ValidationIssue]:
    issues = []
    if d.statement_period_end <= d.statement_period_start:
        issues.append(ValidationIssue(field="statement_period_end", message="End date is not after start date", severity="error"))
    if d.avg_monthly_balance < 0 or d.min_balance < 0:
        issues.append(ValidationIssue(field="min_balance", message="Negative balance reported", severity="error"))
    if d.cash_deposit_ratio is not None and d.cash_deposit_ratio > 0.5:
        issues.append(ValidationIssue(field="cash_deposit_ratio", message="Cash deposits exceed 50% of credits - possible turnover inflation", severity="warning"))
    if d.bounce_count > 5:
        issues.append(ValidationIssue(field="bounce_count", message="High cheque/ECS bounce count", severity="warning"))
    return issues


def check_gst(d: GSTData) -> list[ValidationIssue]:
    issues = []
    if d.filing_status in ("defaulter", "cancelled", "suspended"):
        issues.append(ValidationIssue(field="filing_status", message=f"GST registration status is '{d.filing_status}'", severity="warning"))
    if d.gstr3b_annual_turnover and d.gstr1_annual_turnover:
        diff_pct = abs(d.gstr3b_annual_turnover - d.gstr1_annual_turnover) / max(d.gstr3b_annual_turnover, 1)
        if diff_pct > 0.1:
            issues.append(ValidationIssue(field="gstr3b_annual_turnover", message=f"GSTR-3B vs GSTR-1 turnover differs by {diff_pct:.0%}", severity="warning"))
    if d.vintage_months < 12:
        issues.append(ValidationIssue(field="vintage_months", message="GST vintage under 12 months", severity="warning"))
    return issues


def check_bureau(d: BureauData) -> list[ValidationIssue]:
    issues = []
    if d.dpd_90_plus > 0:
        issues.append(ValidationIssue(field="dpd_90_plus", message="Accounts with 90+ DPD on record", severity="warning"))
    if d.written_off_accounts > 0:
        issues.append(ValidationIssue(field="written_off_accounts", message="Written-off accounts present", severity="error"))
    if d.bureau_score < 650:
        issues.append(ValidationIssue(field="bureau_score", message="Bureau score below 650", severity="warning"))
    return issues


def check_financials(d: FinancialsData) -> list[ValidationIssue]:
    issues = []
    if d.total_liabilities > d.total_assets:
        issues.append(ValidationIssue(field="total_liabilities", message="Liabilities exceed assets (negative net worth)", severity="error"))
    if not d.is_audited:
        issues.append(ValidationIssue(field="is_audited", message="Financials are not audited", severity="warning"))
    if d.debt_equity_ratio > 3:
        issues.append(ValidationIssue(field="debt_equity_ratio", message="Debt/Equity ratio above 3x", severity="warning"))
    return issues


def check_ledger(d: LedgerData) -> list[ValidationIssue]:
    issues = []
    if d.top_debtor_concentration_pct > 70:
        issues.append(ValidationIssue(field="top_debtor_concentration_pct", message="Single debtor exceeds 70% concentration - anchor risk", severity="warning"))
    if d.debtor_days > 120:
        issues.append(ValidationIssue(field="debtor_days", message="Debtor days exceed 120", severity="warning"))
    return issues


def check_kyc(d: KYCData) -> list[ValidationIssue]:
    issues = []
    if d.kyc_doc_status != "complete":
        issues.append(ValidationIssue(field="kyc_doc_status", message=f"KYC docs are '{d.kyc_doc_status}'", severity="warning"))
    if len(d.directors) == 0:
        issues.append(ValidationIssue(field="directors", message="No directors on record", severity="error"))
    return issues


VALIDATORS: Dict[str, Callable] = {
    "banking": check_banking,
    "gst": check_gst,
    "bureau": check_bureau,
    "financials": check_financials,
    "ledger": check_ledger,
    "kyc": check_kyc,
}
