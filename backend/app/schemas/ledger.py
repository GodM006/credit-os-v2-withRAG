from __future__ import annotations

from pydantic import BaseModel, Field


class LedgerData(BaseModel):
    """Extracted from sales ledger, purchase ledger, and invoices."""

    period: str = Field(description="e.g. 'FY2025-26'")
    total_sales: float
    total_purchases: float
    debtor_days: float = Field(description="Average days receivable")
    creditor_days: float = Field(description="Average days payable")
    top_debtor_concentration_pct: float = Field(
        description="% of total receivables owed by the single largest debtor"
    )
    overdue_receivables: float = Field(default=0)
