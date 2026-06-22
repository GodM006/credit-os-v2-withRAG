from __future__ import annotations

from datetime import date
from typing import List, Literal

from pydantic import BaseModel, Field


class Director(BaseModel):
    name: str
    din: str = Field(description="Director Identification Number")
    designation: str


class KYCData(BaseModel):
    """Extracted from company registration, director records, ownership, and KYC docs."""

    legal_name: str
    cin: str = Field(description="Corporate Identification Number")
    pan: str
    incorporation_date: date
    entity_type: Literal["pvt_ltd", "llp", "partnership", "proprietorship", "public_ltd"]
    registered_address: str
    directors: List[Director] = Field(default_factory=list)
    kyc_doc_status: Literal["complete", "incomplete", "pending_verification"]
