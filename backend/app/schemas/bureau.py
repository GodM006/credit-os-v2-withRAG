from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class BureauData(BaseModel):
    """Extracted from commercial + personal credit bureau reports (CIBIL/CRIF/Experian-style)."""

    entity_type: Literal["commercial", "personal"]
    bureau_score: int = Field(ge=300, le=900)
    total_exposure: float = Field(description="Total outstanding credit exposure across lenders, INR")
    overdue_amount: float = Field(default=0)
    dpd_30: int = Field(default=0, description="Number of accounts with 30+ days past due")
    dpd_60: int = Field(default=0)
    dpd_90_plus: int = Field(default=0)
    enquiries_last_6m: int = Field(default=0, description="Hard credit enquiries in the last 6 months")
    written_off_accounts: int = Field(default=0)
    active_accounts: int = Field(default=0)
