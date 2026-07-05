from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator

NULLISH = frozenset({"not provided", "n/a", "na", "none", "unknown", "null", ""})


class FinancialsData(BaseModel):
    """Extracted from P&L, balance sheet, and audited financial statements."""

    period: str = Field(default="", description="e.g. 'FY2025-26'")
    is_audited: bool = Field(default=False)
    revenue: float = Field(default=0.0)
    ebitda: float = Field(default=0.0)
    net_profit: float = Field(default=0.0)
    # These are often missing from partial/unaudited financials — use Optional
    total_assets: Optional[float] = Field(default=None)
    total_liabilities: Optional[float] = Field(default=None)
    net_worth: Optional[float] = Field(default=None)
    debt_equity_ratio: Optional[float] = Field(default=None)

    @field_validator("period", mode="before")
    @classmethod
    def coerce_period(cls, v):
        if v is None:
            return ""
        if str(v).strip().lower() in NULLISH:
            return ""
        return str(v).strip()

    @field_validator("is_audited", mode="before")
    @classmethod
    def coerce_is_audited(cls, v):
        if isinstance(v, bool):
            return v
        if v is None:
            return False
        s = str(v).strip().lower()
        if s in NULLISH:
            return False
        return s in ("true", "yes", "1", "audited")

    @field_validator(
        "revenue", "ebitda", "net_profit",
        mode="before"
    )
    @classmethod
    def coerce_float_required(cls, v):
        if v is None:
            return 0.0
        s = str(v).strip().lower()
        if s in NULLISH:
            return 0.0
        try:
            clean = str(v).replace(",", "").replace("₹", "").replace("(", "-").replace(")", "").strip()
            return float(clean)
        except (TypeError, ValueError):
            return 0.0

    @field_validator(
        "total_assets", "total_liabilities", "net_worth", "debt_equity_ratio",
        mode="before"
    )
    @classmethod
    def coerce_float_optional(cls, v):
        if v is None:
            return None
        s = str(v).strip().lower()
        if s in NULLISH:
            return None
        try:
            clean = str(v).replace(",", "").replace("₹", "").replace("(", "-").replace(")", "").strip()
            return float(clean)
        except (TypeError, ValueError):
            return None
