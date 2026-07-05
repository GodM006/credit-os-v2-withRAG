"""
Assembles all data from AppState into a structured Credit Appraisal Memorandum
(CAM) dictionary. This is pure data extraction — no LLM call. The LLM-generated
narrative from credit_memo.py is injected as the analyst observations section.

All twelve sections of a standard bank CAM format are populated here:
  S1  Basic Information (KYC)
  S2  Credit Requirement
  S3  Financial Analysis
  S4  Banking Analysis
  S5  Bureau & Credit History
  S6  GST & Compliance
  S7  Triangulation Analysis (trust weights, effective metrics)
  S8  Fraud & Risk Assessment
  S9  Policy Compliance (BRE results)
  S10 ML Risk Scoring
  S11 Limit Optimisation (constraint waterfall)
  S12 Analyst Observations (LLM narrative, injected separately)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _fmt_inr(n: Optional[float]) -> str:
    if n is None:
        return "N/A"
    if abs(n) >= 10_000_000:
        return f"Rs {n / 10_000_000:.2f} Cr"
    if abs(n) >= 100_000:
        return f"Rs {n / 100_000:.2f} L"
    return f"Rs {n:,.0f}"


def _pct(n: Optional[float], decimals: int = 1) -> str:
    if n is None:
        return "N/A"
    return f"{n * 100:.{decimals}f}%"


def _val(v: Any, suffix: str = "") -> str:
    if v is None:
        return "N/A"
    if isinstance(v, float) and v == int(v):
        return f"{int(v)}{suffix}"
    if isinstance(v, float):
        return f"{v:.2f}{suffix}"
    return f"{v}{suffix}"


def build_cam(state: Dict[str, Any]) -> Dict[str, Any]:
    src = state.get("source_jsons", {})
    em = state.get("effective_metrics", {})
    ps = state.get("policy_summary", {})
    tw = state.get("trust_weights", {})
    limit_info = (state.get("evidence_map") or {}).get("limit_optimiser", {})

    kyc = (src.get("kyc") or {}).get("data") or {}
    gst = (src.get("gst") or {}).get("data") or {}
    bureau = (src.get("bureau") or {}).get("data") or {}
    financials = (src.get("financials") or {}).get("data") or {}
    ledger = (src.get("ledger") or {}).get("data") or {}
    banking = (src.get("banking") or {}).get("data") or {}

    pairwise = tw.get("pairwise", {})
    aggregated = tw.get("aggregated", {})
    fraud_signals = state.get("fraud_signals", [])
    contradictions = state.get("contradictions", [])
    rule_results = ps.get("rule_results", [])
    constraints = limit_info.get("constraints", {})

    directors = ", ".join(d.get("name", "") for d in (kyc.get("directors") or []))
    accounts = banking.get("accounts") or [{}]
    bank_names = ", ".join(
        a.get("bank_name", "N/A") for a in accounts if isinstance(a, dict)
    )

    return {
        "meta": {
            "case_id": state.get("case_id", "N/A"),
            "company_name": kyc.get("legal_name") or state.get("company_name", "N/A"),
            "generated_at": datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC"),
            "prepared_by": "Credit Decisioning OS — Agentic AI Pipeline v1.0",
        },
        "s1_basic_info": {
            "title": "SECTION 1 — BASIC INFORMATION",
            "rows": [
                ("Legal Name", kyc.get("legal_name", "N/A")),
                ("CIN", kyc.get("cin", "N/A")),
                ("PAN", kyc.get("pan", "N/A")),
                ("GSTIN", gst.get("gstin", "N/A")),
                ("Date of Incorporation", _val(kyc.get("incorporation_date"))),
                ("Entity Type", _val(kyc.get("entity_type", "N/A")).replace("_", " ").title()),
                ("Registered Address", kyc.get("registered_address", "N/A")),
                ("Directors / Partners", directors or "N/A"),
                ("KYC Document Status", _val(kyc.get("kyc_doc_status", "N/A")).replace("_", " ").title()),
            ],
        },
        "s2_credit_requirement": {
            "title": "SECTION 2 — CREDIT REQUIREMENT",
            "rows": [
                ("Facility Type", "Working Capital Loan"),
                ("Recommended Limit", _fmt_inr(state.get("recommended_limit"))),
                ("Purpose", "Short-term working capital requirement"),
                ("Tenor", "12 months (renewable)"),
                ("Repayment", "Monthly installments / Demand basis"),
                ("Binding Constraint", _val(limit_info.get("binding_constraint", "N/A")).replace("_", " ")),
                ("Risk Multiplier Applied", _pct(limit_info.get("risk_multiplier", 1.0), 0)),
            ],
        },
        "s3_financial_analysis": {
            "title": "SECTION 3 — FINANCIAL ANALYSIS",
            "period": financials.get("period", "FY2025-26"),
            "is_audited": "Yes" if financials.get("is_audited") else "No (Management Accounts)",
            "pnl_rows": [
                ("Revenue / Turnover", _fmt_inr(financials.get("revenue"))),
                ("EBITDA", _fmt_inr(financials.get("ebitda"))),
                ("Net Profit", _fmt_inr(financials.get("net_profit"))),
            ],
            "bs_rows": [
                ("Total Assets", _fmt_inr(financials.get("total_assets"))),
                ("Total Liabilities", _fmt_inr(financials.get("total_liabilities"))),
                ("Net Worth", _fmt_inr(financials.get("net_worth"))),
                ("Debt / Equity Ratio", _val(financials.get("debt_equity_ratio"), "x")),
            ],
            "ledger_rows": [
                ("Total Sales (Ledger)", _fmt_inr(ledger.get("total_sales"))),
                ("Total Purchases", _fmt_inr(ledger.get("total_purchases"))),
                ("Debtor Days", _val(ledger.get("debtor_days"), " days")),
                ("Creditor Days", _val(ledger.get("creditor_days"), " days")),
                ("Top Debtor Concentration", _val(ledger.get("top_debtor_concentration_pct"), "%")),
                ("Overdue Receivables", _fmt_inr(ledger.get("overdue_receivables"))),
            ],
        },
        "s4_banking": {
            "title": "SECTION 4 — BANKING ANALYSIS",
            "rows": [
                ("Banks / Accounts", bank_names),
                ("Statement Period",
                 f"{_val(banking.get('statement_period_start'))} to {_val(banking.get('statement_period_end'))}"),
                ("Total Credits (Period)", _fmt_inr(banking.get("total_credits"))),
                ("Total Debits (Period)", _fmt_inr(banking.get("total_debits"))),
                ("Average Monthly Balance", _fmt_inr(banking.get("avg_monthly_balance"))),
                ("Minimum Balance Observed", _fmt_inr(banking.get("min_balance"))),
                ("Cheque / ECS Bounces", _val(banking.get("bounce_count"), " instances")),
                ("Cash Deposit Ratio", _pct(banking.get("cash_deposit_ratio"), 1)),
                ("Bank-Inferred Annual Turnover", _fmt_inr(banking.get("inferred_annual_turnover"))),
            ],
        },
        "s5_bureau": {
            "title": "SECTION 5 — BUREAU & CREDIT HISTORY",
            "rows": [
                ("Bureau Score", _val(bureau.get("bureau_score"))),
                ("Total Credit Exposure", _fmt_inr(bureau.get("total_exposure"))),
                ("Overdue Amount", _fmt_inr(bureau.get("overdue_amount"))),
                ("Accounts — 30 DPD", _val(bureau.get("dpd_30"), " account(s)")),
                ("Accounts — 60 DPD", _val(bureau.get("dpd_60"), " account(s)")),
                ("Accounts — 90+ DPD", _val(bureau.get("dpd_90_plus"), " account(s)")),
                ("Hard Enquiries (6M)", _val(bureau.get("enquiries_last_6m"))),
                ("Written-off Accounts", _val(bureau.get("written_off_accounts"))),
                ("Active Accounts", _val(bureau.get("active_accounts"))),
            ],
        },
        "s6_gst": {
            "title": "SECTION 6 — GST & COMPLIANCE",
            "rows": [
                ("GSTIN", gst.get("gstin", "N/A")),
                ("GST Registration Date", _val(gst.get("registration_date"))),
                ("GST Vintage", _val(gst.get("vintage_months"), " months")),
                ("Filing Frequency", _val(gst.get("filing_frequency", "N/A")).title()),
                ("Filing Status", _val(gst.get("filing_status", "N/A")).title()),
                ("Last Filed Period", gst.get("last_filed_period", "N/A")),
                ("GSTR-3B Turnover (Annual)", _fmt_inr(gst.get("gstr3b_annual_turnover"))),
                ("GSTR-1 Turnover (Annual)", _fmt_inr(gst.get("gstr1_annual_turnover"))),
                ("Late Filings (12M)", _val(gst.get("late_filings_last_12m"), " filing(s)")),
            ],
        },
        "s7_triangulation": {
            "title": "SECTION 7 — TRIANGULATION ANALYSIS",
            "pairwise_rows": [
                (
                    label.replace("_", " ").upper(),
                    _fmt_inr(pair.get("value_a")),
                    _fmt_inr(pair.get("value_b")),
                    f"{pair.get('variance_pct', 0) * 100:.1f}%",
                    f"{pair.get('trust_weight', 0):.2f}",
                )
                for label, pair in pairwise.items()
            ],
            "source_weights": [
                (src_name.upper(), f"{weight:.2f}")
                for src_name, weight in aggregated.items()
            ],
            "effective_rows": [
                ("Effective Turnover (Reconciled)", _fmt_inr(em.get("effective_turnover"))),
                ("Confidence Level", _pct(em.get("confidence"), 0)),
                ("WC Gap — Nayak Method (20%)", _fmt_inr(
                    (em.get("working_capital_gap_methods") or {}).get("turnover_method_20pct"))),
                ("WC Gap — Operating Cycle", _fmt_inr(
                    (em.get("working_capital_gap_methods") or {}).get("operating_cycle"))),
                ("Working Capital Gap (Used)", _fmt_inr(em.get("working_capital_gap"))),
                ("Repayment Capacity (EBITDA basis)", _fmt_inr(em.get("repayment_capacity"))),
                ("Current DSCR", _val(em.get("current_dscr"), "x") if em.get("current_dscr") else "N/A (no existing debt)"),
            ],
        },
        "s8_fraud": {
            "title": "SECTION 8 — FRAUD & RISK ASSESSMENT",
            "fraud_risk": (em.get("fraud_risk") or "N/A").upper(),
            "signals": [
                (s.get("type", "").replace("_", " ").title(), s.get("severity", "").upper(), s.get("message", ""))
                for s in fraud_signals
            ],
            "contradictions": [
                (c.get("pair", "").replace("_", " ").upper(),
                 f"{c.get('variance_pct', 0) * 100:.1f}%",
                 c.get("message", ""))
                for c in contradictions
            ],
        },
        "s9_policy": {
            "title": "SECTION 9 — POLICY COMPLIANCE (BRE)",
            "decision": (ps.get("policy_decision") or "N/A").upper().replace("_", " "),
            "pass_rate": f"{ps.get('rule_pass_rate', 0)}%",
            "deviation_flag": "Yes" if ps.get("deviation_flag") else "No",
            "rule_rows": [
                (
                    r.get("label", ""),
                    "PASS" if r.get("passed") else "FAIL",
                    _val(r.get("value")),
                    _val(r.get("threshold")),
                    r.get("note", ""),
                )
                for r in rule_results
            ],
        },
        "s10_ml": {
            "title": "SECTION 10 — ML RISK ASSESSMENT",
            "rows": [
                ("Risk Score", f"{_val(state.get('risk_score'))} / 83"),
                ("Risk Band", em.get("risk_band", "N/A")),
                ("Probability of Default (PD)", _pct(state.get("pd"), 2)),
                ("Loss Given Default (LGD)", _pct(state.get("lgd"), 1)),
                ("Expected Loss Rate", _pct(em.get("expected_loss_rate"), 2)),
                ("Model Used", em.get("ml_model_name", "N/A")),
                ("Training Data", em.get("ml_trained_on", "N/A").title()),
            ],
        },
        "s11_limit": {
            "title": "SECTION 11 — LIMIT OPTIMISATION",
            "constraint_rows": [
                ("C1 — Policy Cap (20% of Turnover)", _fmt_inr(constraints.get("C1_policy_cap_20pct_turnover"))),
                ("C2 — Working Capital Need", _fmt_inr(constraints.get("C2_working_capital_need"))),
                ("C3 — Repayment Capacity", _fmt_inr(constraints.get("C3_repayment_capacity"))),
                ("C4 — Risk Appetite Adjusted", _fmt_inr(constraints.get("C4_risk_appetite_adjusted"))),
                ("C5 — Exposure Headroom", _fmt_inr(constraints.get("C5_exposure_headroom"))),
            ],
            "recommended_limit": _fmt_inr(state.get("recommended_limit")),
            "binding_constraint": _val(limit_info.get("binding_constraint", "N/A")).replace("_", " "),
            "note": limit_info.get("note", ""),
        },
    }
