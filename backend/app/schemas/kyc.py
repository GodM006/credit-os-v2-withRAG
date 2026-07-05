from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

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


class Director(BaseModel):
    name: str = Field(default="")
    din: str = Field(default="", description="Director Identification Number")
    designation: str = Field(default="")


class KYCData(BaseModel):
    """Extracted from company registration, director records, ownership, and KYC docs."""

    legal_name: str = Field(default="")
    cin: str = Field(default="", description="Corporate Identification Number")
    pan: str = Field(default="")
    # Optional: proprietorships and some entities may not have incorporation date in docs
    incorporation_date: Optional[date] = None
    entity_type: Optional[Literal["pvt_ltd", "llp", "partnership", "proprietorship", "public_ltd"]] = None
    registered_address: str = Field(default="")
    directors: list[Director] = Field(default_factory=list)
    kyc_doc_status: Optional[Literal["complete", "incomplete", "pending_verification"]] = None

    @field_validator("incorporation_date", mode="before")
    @classmethod
    def coerce_incorporation_date(cls, v):
        return parse_custom_date(v)

    @field_validator("entity_type", mode="before")
    @classmethod
    def coerce_entity_type(cls, v):
        if not v or str(v).strip().lower() in NULLISH:
            return None
        return v

    @field_validator("kyc_doc_status", mode="before")
    @classmethod
    def coerce_kyc_doc_status(cls, v):
        if not v or str(v).strip().lower() in NULLISH:
            return None
        return v
