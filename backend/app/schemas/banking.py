from __future__ import annotations

from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

NULLISH = frozenset({"not provided", "n/a", "na", "none", "unknown", "null", ""})


def parse_custom_date(v) -> date | None:
    if v is None:
        return None
    s = str(v).strip()
    if s.lower() in NULLISH:
        return None
    # Support various input formats like YYYY-MM-DD, DD-MM-YYYY, DD/MM/YYYY, etc.
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


class BankAccountSummary(BaseModel):
    bank_name: str = Field(default="")
    account_type: Optional[Literal["current", "savings", "cc_od"]] = None
    account_number_masked: str = Field(default="", description="Last 4 digits only, e.g. XXXX1234")

    @field_validator("account_type", mode="before")
    @classmethod
    def coerce_account_type(cls, v):
        if not v or str(v).strip().lower() in NULLISH:
            return None
        return v


class BankCounterparty(BaseModel):
    """A counterparty extracted from bank statement narrations (best-effort)."""

    name: str = Field(default="", description="Counterparty name as best extracted from transaction narration")
    direction: Literal["inflow", "outflow"] = Field(default="inflow")
    total_amount: float = Field(default=0.0, description="Sum of absolute transaction amounts for this counterparty")
    transaction_count: int = Field(default=0)
    confidence: Literal["high", "medium", "low"] = Field(
        default="low",
        description="high=name appears consistently/clearly; low=inferred from partial narration"
    )

    @field_validator("total_amount", mode="before")
    @classmethod
    def coerce_amount(cls, v):
        if v is None:
            return 0.0
        try:
            return abs(float(str(v).replace(",", "").replace("₹", "").strip()))
        except (TypeError, ValueError):
            return 0.0


class BankRiskEvent(BaseModel):
    """An itemized risk event flagged from bank statement transactions."""

    event_type: Literal["nach_ecs_bounce", "emi_like_debit", "gst_penalty_or_demand_debit", "large_cash_withdrawal"] = Field(
        default="nach_ecs_bounce"
    )
    event_date: Optional[str] = Field(default=None, description="Date of transaction, YYYY-MM-DD or DD-MM-YYYY")
    amount: float = Field(default=0.0)
    narration_snippet: str = Field(default="", description="Relevant snippet from transaction narration")
    confidence: Literal["high", "medium", "low"] = Field(default="low")

    @field_validator("amount", mode="before")
    @classmethod
    def coerce_amount(cls, v):
        if v is None:
            return 0.0
        try:
            return abs(float(str(v).replace(",", "").replace("₹", "").strip()))
        except (TypeError, ValueError):
            return 0.0

    @field_validator("event_date", "narration_snippet", mode="before")
    @classmethod
    def coerce_str_nullish(cls, v):
        if not v or str(v).strip().lower() in NULLISH:
            return ""
        return str(v).strip()

    @field_validator("event_type", mode="before")
    @classmethod
    def coerce_event_type(cls, v):
        allowed = {"nach_ecs_bounce", "emi_like_debit", "gst_penalty_or_demand_debit", "large_cash_withdrawal"}
        s = str(v).strip().lower() if v else "nach_ecs_bounce"
        return s if s in allowed else "nach_ecs_bounce"

    @field_validator("confidence", mode="before")
    @classmethod
    def coerce_confidence(cls, v):
        allowed = {"high", "medium", "low"}
        s = str(v).strip().lower() if v else "low"
        return s if s in allowed else "low"


class BankingData(BaseModel):
    """Extracted from bank statements / Account Aggregator (AA) feed / Open Banking."""

    entity_name: str = Field(default="")
    statement_period_start: Optional[date] = None
    statement_period_end: Optional[date] = None
    accounts: List[BankAccountSummary] = Field(default_factory=list)
    total_credits: float = Field(default=0.0, description="Sum of all credits over the statement period, in INR")
    total_debits: float = Field(default=0.0)
    avg_monthly_balance: float = Field(default=0.0)
    min_balance: float = Field(default=0.0)
    bounce_count: int = Field(default=0, description="Count of bounced cheques / failed ECS/NACH in the period")
    inferred_annual_turnover: float = Field(default=0.0, description="Annualised turnover inferred from bank credits")
    cash_deposit_ratio: Optional[float] = Field(
        default=None, description="Cash deposits / total credits. High values are a fraud/risk signal."
    )
    # Named counterparties — new multi-hop graph nodes (best-effort from narration)
    top_counterparties: List[BankCounterparty] = Field(
        default_factory=list,
        description="Top counterparties by amount: up to 5 inflow + 5 outflow, extracted from narrations"
    )
    risk_events: List[BankRiskEvent] = Field(
        default_factory=list,
        description="Itemized risk transactions flagged from narrations (e.g. NACH bounce, EMI debit, GST penalty, cash withdrawal)"
    )


    @field_validator("statement_period_start", "statement_period_end", mode="before")
    @classmethod
    def coerce_date_nullish(cls, v):
        return parse_custom_date(v)

    @field_validator(
        "total_credits",
        "total_debits",
        "avg_monthly_balance",
        "min_balance",
        "inferred_annual_turnover",
        mode="before"
    )
    @classmethod
    def coerce_float_nullish(cls, v):
        if v is None:
            return 0.0
        if str(v).strip().lower() in NULLISH:
            return 0.0
        try:
            clean_val = str(v).replace(",", "").replace("₹", "").strip()
            return abs(float(clean_val))
        except (TypeError, ValueError):
            return 0.0
