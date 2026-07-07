from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

NULLISH = frozenset({"not provided", "n/a", "na", "none", "unknown", "null", ""})


class LedgerCounterparty(BaseModel):
    """A named buyer (debtor) or supplier (creditor) extracted from the sales/purchase ledger."""

    name: str = Field(default="")
    gstin: Optional[str] = Field(default=None, description="GSTIN of buyer/supplier if present in ledger column")
    total_invoice_value: float = Field(default=0.0)
    pct_of_total: Optional[float] = Field(default=None, description="% of total sales (debtors) or purchases (creditors)")
    role: Literal["debtor", "creditor"] = Field(default="debtor")

    @field_validator("gstin", mode="before")
    @classmethod
    def coerce_gstin(cls, v):
        if not v or str(v).strip().lower() in NULLISH:
            return None
        return str(v).strip()

    @field_validator("name", mode="before")
    @classmethod
    def coerce_name(cls, v):
        if not v or str(v).strip().lower() in NULLISH:
            return ""
        return str(v).strip()

    @field_validator("total_invoice_value", mode="before")
    @classmethod
    def coerce_total_invoice_value(cls, v):
        if v is None or str(v).strip().lower() in NULLISH:
            return 0.0
        try:
            return float(str(v).replace(",", "").replace("₹", "").strip())
        except (TypeError, ValueError):
            return 0.0

    @field_validator("pct_of_total", mode="before")
    @classmethod
    def coerce_pct_of_total(cls, v):
        if v is None or str(v).strip().lower() in NULLISH:
            return None
        try:
            return float(str(v).replace(",", "").replace("₹", "").strip())
        except (TypeError, ValueError):
            return None


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
    # Named counterparties — new multi-hop graph nodes
    top_debtors: List[LedgerCounterparty] = Field(
        default_factory=list,
        description="Top 5 buyers by Invoice Value from the sales ledger"
    )
    top_creditors: List[LedgerCounterparty] = Field(
        default_factory=list,
        description="Top 5 suppliers by Invoice Value from the purchase ledger"
    )

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
    def coerce_float_nullish_main(cls, v):
        if v is None:
            return None
        if str(v).strip().lower() in NULLISH:
            return None
        try:
            clean_val = str(v).replace(",", "").replace("₹", "").strip()
            return float(clean_val)
        except (TypeError, ValueError):
            return None
