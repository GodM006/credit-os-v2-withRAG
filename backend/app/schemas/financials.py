from __future__ import annotations

from pydantic import BaseModel, Field


class FinancialsData(BaseModel):
    """Extracted from P&L, balance sheet, and audited financial statements."""

    period: str = Field(description="e.g. 'FY2025-26'")
    is_audited: bool
    revenue: float
    ebitda: float
    net_profit: float
    total_assets: float
    total_liabilities: float
    net_worth: float
    debt_equity_ratio: float
