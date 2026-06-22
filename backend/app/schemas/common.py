"""
Shared types used by every Layer 1 agent.

ExtractionResult is the uniform "envelope" every agent returns, regardless of
which source it's reading. This is what gets written into source_jsons in the
shared working memory (AppState), so Layer 2+ can consume any source the same way.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Generic, List, Literal, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T", bound=BaseModel)


class ValidationIssue(BaseModel):
    field: str
    message: str
    severity: Literal["error", "warning"] = "error"


class ExtractionResult(BaseModel, Generic[T]):
    source: str
    data: Optional[T] = None
    confidence: float = Field(ge=0.0, le=1.0)
    validation_status: Literal["valid", "valid_with_warnings", "invalid"]
    issues: List[ValidationIssue] = Field(default_factory=list)
    raw_excerpt: str
    model_used: str
    attempts: int = 1
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
