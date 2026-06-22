from __future__ import annotations

from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class BankAccountSummary(BaseModel):
    bank_name: str
    account_type: Literal["current", "savings", "cc_od"]
    account_number_masked: str = Field(description="Last 4 digits only, e.g. XXXX1234")


class BankingData(BaseModel):
    """Extracted from bank statements / Account Aggregator (AA) feed / Open Banking."""

    entity_name: str
    statement_period_start: date
    statement_period_end: date
    accounts: List[BankAccountSummary] = Field(default_factory=list)
    total_credits: float = Field(description="Sum of all credits over the statement period, in INR")
    total_debits: float
    avg_monthly_balance: float
    min_balance: float
    bounce_count: int = Field(default=0, description="Count of bounced cheques / failed ECS/NACH in the period")
    inferred_annual_turnover: float = Field(description="Annualised turnover inferred from bank credits")
    cash_deposit_ratio: Optional[float] = Field(
        default=None, description="Cash deposits / total credits. High values are a fraud/risk signal."
    )
