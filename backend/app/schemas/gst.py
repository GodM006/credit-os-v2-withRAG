from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

NULLISH = frozenset({"not provided", "n/a", "na", "none", "unknown", "null", ""})


def parse_custom_date(v) -> date | None:
    if v is None:
        return None
    s = str(v).strip()
    if s.lower() in NULLISH:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


class GSTData(BaseModel):
    """Extracted from GST/VAT registration + ITR + GSTR-1 / GSTR-3B filings.
    All fields are Optional so that cases without a GST document still produce
    a usable (partial) result rather than a hard validation failure.
    """

    gstin: Optional[str] = Field(default=None, description="15-character GSTIN")
    legal_name: Optional[str] = Field(default=None)
    registration_date: Optional[date] = Field(default=None)
    filing_frequency: Optional[str] = Field(default=None, description="'monthly' or 'quarterly'")
    last_filed_period: Optional[str] = Field(default=None, description="e.g. 'Mar-2026'")
    filing_status: Optional[str] = Field(default=None, description="regular/defaulter/cancelled/suspended")
    gstr3b_annual_turnover: Optional[float] = Field(default=None, description="Annual turnover as per GSTR-3B, INR")
    gstr1_annual_turnover: Optional[float] = Field(default=None, description="Annual turnover as per GSTR-1, INR")
    vintage_months: Optional[int] = Field(default=None, description="Months since GST registration")
    late_filings_last_12m: int = Field(default=0)

    @field_validator("gstin", "legal_name", "last_filed_period", "filing_frequency", "filing_status", mode="before")
    @classmethod
    def coerce_str_nullish(cls, v):
        if v is None:
            return None
        if str(v).strip().lower() in NULLISH:
            return None
        return v

    @field_validator("registration_date", mode="before")
    @classmethod
    def coerce_registration_date(cls, v):
        return parse_custom_date(v)

    @field_validator("gstr3b_annual_turnover", "gstr1_annual_turnover", mode="before")
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

    @field_validator("vintage_months", mode="before")
    @classmethod
    def coerce_int_nullish(cls, v):
        if v is None:
            return None
        if str(v).strip().lower() in NULLISH:
            return None
        try:
            clean_val = str(v).replace(",", "").replace("₹", "").strip()
            return int(float(clean_val))
        except (TypeError, ValueError):
            return None
