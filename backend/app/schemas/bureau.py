from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

NULLISH = frozenset({"not provided", "n/a", "na", "none", "unknown", "null", ""})


class LoanFacility(BaseModel):
    """One row from the itemized credit facility / account information table in a bureau report."""

    lender_name: str = Field(default="")
    facility_type: str = Field(default="", description="e.g. 'Term Loan', 'CC', 'OD', 'LC', 'Home Loan'")
    sanctioned_amount: float = Field(default=0.0)
    outstanding_amount: float = Field(default=0.0)
    dpd_bucket: str = Field(default="0", description="DPD category: '0', '30', '60', '90+', 'NPA'")
    account_status: str = Field(
        default="",
        description="'active', 'closed', 'written_off', 'settled', 'NPA'"
    )
    guarantor_name: str = Field(
        default="",
        description="Name of personal guarantor or co-borrower if listed for this account"
    )

    @field_validator("sanctioned_amount", "outstanding_amount", mode="before")
    @classmethod
    def coerce_amount(cls, v):
        if v is None:
            return 0.0
        if str(v).strip().lower() in NULLISH:
            return 0.0
        try:
            return float(str(v).replace(",", "").replace("₹", "").strip())
        except (TypeError, ValueError):
            return 0.0

    @field_validator("lender_name", "facility_type", "dpd_bucket", "account_status", "guarantor_name", mode="before")

    @classmethod
    def coerce_str_nullish(cls, v):
        if not v or str(v).strip().lower() in NULLISH:
            return ""
        return str(v).strip()


class CreditEnquiry(BaseModel):
    """One row from the itemized ENQUIRY section of a commercial or personal bureau report."""

    lender_name: str = Field(default="")
    enquiry_date: Optional[str] = Field(default=None, description="Date of enquiry, YYYY-MM-DD or DD-MM-YYYY format")
    purpose: str = Field(default="", description="Purpose or loan type enquired for, e.g. 'Working Capital', 'CC', 'Personal Loan'")
    amount: float = Field(default=0.0)

    @field_validator("amount", mode="before")
    @classmethod
    def coerce_amount(cls, v):
        if v is None or str(v).strip().lower() in NULLISH:
            return 0.0
        try:
            return float(str(v).replace(",", "").replace("₹", "").strip())
        except (TypeError, ValueError):
            return 0.0

    @field_validator("lender_name", "enquiry_date", "purpose", mode="before")
    @classmethod
    def coerce_str_nullish(cls, v):
        if not v or str(v).strip().lower() in NULLISH:
            return ""
        return str(v).strip()


class PersonalBureauEntry(BaseModel):
    """Personal CIR data for one director/guarantor, extracted from a combined bureau report."""

    director_name: str = Field(default="", description="Name as it appears in the personal CIR header")
    director_pan: Optional[str] = Field(default=None, description="PAN number from the personal CIR, if present")
    bureau_score: Optional[int] = Field(default=None, description="Consumer credit score (e.g. CIBIL TransUnion score)")
    total_exposure: float = Field(default=0.0)
    overdue_amount: float = Field(default=0.0)
    dpd_30: int = Field(default=0)
    dpd_60: int = Field(default=0)
    dpd_90_plus: int = Field(default=0)
    enquiries_last_6m: int = Field(default=0)
    written_off_accounts: int = Field(default=0)
    active_accounts: int = Field(default=0)
    facilities: List[LoanFacility] = Field(
        default_factory=list,
        description="Itemized credit facilities from the ACCOUNT INFORMATION section of this personal CIR"
    )
    enquiries: List[CreditEnquiry] = Field(
        default_factory=list,
        description="Itemized credit enquiries from the ENQUIRY section of this personal CIR"
    )



    @field_validator(
        "dpd_30", "dpd_60", "dpd_90_plus", "enquiries_last_6m", "written_off_accounts", "active_accounts",
        mode="before"
    )
    @classmethod
    def coerce_int_nullish(cls, v):
        if v is None or str(v).strip().lower() in NULLISH:
            return 0
        try:
            return int(float(str(v).replace(",", "").strip()))
        except (TypeError, ValueError):
            return 0

    @field_validator("director_pan", mode="before")
    @classmethod
    def coerce_pan(cls, v):
        if not v or str(v).strip().lower() in NULLISH:
            return None
        return str(v).strip().upper()

    @field_validator("bureau_score", mode="before")
    @classmethod
    def coerce_bureau_score(cls, v):
        if not v or str(v).strip().lower() in NULLISH:
            return None
        try:
            return int(float(str(v).replace(",", "").strip()))
        except (TypeError, ValueError):
            return None

    @field_validator("total_exposure", "overdue_amount", mode="before")
    @classmethod
    def coerce_float_nullish(cls, v):
        if v is None:
            return 0.0
        if str(v).strip().lower() in NULLISH:
            return 0.0
        try:
            return float(str(v).replace(",", "").replace("₹", "").strip())
        except (TypeError, ValueError):
            return 0.0


class BureauData(BaseModel):
    """Extracted from commercial + personal credit bureau reports (CIBIL/CRIF/Experian-style).

    Fields 1–10 (existing aggregates) apply to the COMMERCIAL report.
    `personal_entries` carries one entry per personal CIR found in the document.
    `facilities` carries the itemized loan facility table from the commercial report.
    All new fields are optional lists that default to [] — fully backward compatible.
    """

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
    # Itemized loan facilities from the commercial bureau report

    @field_validator(
        "dpd_30", "dpd_60", "dpd_90_plus", "enquiries_last_6m", "written_off_accounts", "active_accounts",
        mode="before"
    )
    @classmethod
    def coerce_int_nullish(cls, v):
        if v is None or str(v).strip().lower() in NULLISH:
            return 0
        try:
            return int(float(str(v).replace(",", "").strip()))
        except (TypeError, ValueError):
            return 0
    facilities: List[LoanFacility] = Field(
        default_factory=list,
        description="Itemized credit facilities from the CREDIT FACILITY DETAILS section"
    )
    enquiries: List[CreditEnquiry] = Field(
        default_factory=list,
        description="Itemized credit enquiries from the ENQUIRY section of the commercial report"
    )

    # Personal CIR entries for directors/guarantors found in the same document
    personal_entries: List[PersonalBureauEntry] = Field(
        default_factory=list,
        description="One entry per personal CIR (director/guarantor) found in the uploaded bureau document"
    )

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
