from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator

NULLISH = frozenset({"not provided", "n/a", "na", "none", "unknown", "null", ""})


class LedgerData(BaseModel):
    """Extracted from sales ledger, purchase ledger, and invoices."""

    period: Optional[str] = Field(default=None, description="e.g. 'FY2025-26'")
    total_sales: Optional[float] = Field(default=None)
    total_purchases: Optional[float] = Field(default=None)
    debtor_days: Optional[float] = Field(default=None, description="Average days receivable")
    creditor_days: Optional[float] = Field(default=None, description="Average days payable")
    top_debtor_concentration_pct: Optional[float] = Field(
        default=None, description="% of total receivables owed by the single largest debtor"
    )
    overdue_receivables: Optional[float] = Field(default=0.0)

    @field_validator("period", mode="before")
    @classmethod
    def coerce_period(cls, v):
        if v is None:
            return None
        if str(v).strip().lower() in NULLISH:
            return None
        return v

    @field_validator(
        "total_sales",
        "total_purchases",
        "debtor_days",
        "creditor_days",
        "top_debtor_concentration_pct",
        "overdue_receivables",
        mode="before"
    )
    @classmethod
    def coerce_float_nullish(cls, v):
        if v is None:
            return None
        if str(v).strip().lower() in NULLISH:
            return None
        try:
            clean_val = str(v).replace(",", "").replace("₹", "").strip()
            return float(clean_val)
        except (TypeError, ValueError):
            return None
