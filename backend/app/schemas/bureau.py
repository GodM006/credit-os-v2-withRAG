from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class BureauData(BaseModel):
    """Extracted from commercial + personal credit bureau reports (CIBIL/CRIF/Experian-style)."""

    entity_type: Optional[Literal["commercial", "personal"]] = None
    # ge=300 removed: if doc is missing/score not available, LLM may return 0 or None
    bureau_score: Optional[int] = Field(default=None, description="Bureau score (300–900 range)")
    total_exposure: float = Field(default=0.0, description="Total outstanding credit exposure across lenders, INR")
    overdue_amount: float = Field(default=0)
    dpd_30: int = Field(default=0, description="Number of accounts with 30+ days past due")
    dpd_60: int = Field(default=0)
    dpd_90_plus: int = Field(default=0)
    enquiries_last_6m: int = Field(default=0, description="Hard credit enquiries in the last 6 months")
    written_off_accounts: int = Field(default=0)
    active_accounts: int = Field(default=0)

    @field_validator("entity_type", mode="before")
    @classmethod
    def coerce_entity_type(cls, v):
        if not v or str(v).strip().lower() in ("not provided", "n/a", "na", "none", "unknown", ""):
            return None
        return v

    @field_validator("bureau_score", mode="before")
    @classmethod
    def coerce_bureau_score(cls, v):
        if not v or str(v).strip().lower() in ("not provided", "n/a", "na", "none", "unknown", ""):
            return None
        s = str(v).strip()
        # Handle CMR rank strings like "CMR-6", "CMR 6", "cmr6" -> numeric score
        import re
        cmr_match = re.search(r"cmr[-\s]?(\d+)", s, re.IGNORECASE)
        if cmr_match:
            cmr_map = {1: 900, 2: 800, 3: 720, 4: 650, 5: 580, 6: 520, 7: 460, 8: 400, 9: 350, 10: 300}
            rank = int(cmr_match.group(1))
            return cmr_map.get(rank, 500)
        try:
            return int(float(s.replace(",", "")))
        except (TypeError, ValueError):
            return None
