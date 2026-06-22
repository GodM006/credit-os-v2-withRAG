from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class GSTData(BaseModel):
    """Extracted from GST/VAT registration + ITR + GSTR-1 / GSTR-3B filings."""

    gstin: str
    legal_name: str
    registration_date: date
    filing_frequency: Literal["monthly", "quarterly"]
    last_filed_period: str = Field(description="e.g. 'Mar-2026'")
    filing_status: Literal["regular", "defaulter", "cancelled", "suspended"]
    gstr3b_annual_turnover: float = Field(description="Annual turnover as per GSTR-3B filings, INR")
    gstr1_annual_turnover: float = Field(description="Annual turnover as per GSTR-1 filings, INR")
    vintage_months: int = Field(description="Months since GST registration")
    late_filings_last_12m: int = Field(default=0)
