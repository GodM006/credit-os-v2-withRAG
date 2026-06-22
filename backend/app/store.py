"""
In-memory store for case state, keyed by case_id.

This is intentionally the simplest possible thing that works for local dev
and demos. When you move past Layer 1, swap this for Redis (matches the
"shared working memory" framing nicely) or a Postgres table without changing
any router code - just the get/set/list functions below.
"""
from __future__ import annotations

from typing import Any, Dict

_CASES: Dict[str, Dict[str, Any]] = {}


def save_case(case_id: str, state: dict) -> None:
    _CASES[case_id] = state


def get_case(case_id: str) -> dict | None:
    return _CASES.get(case_id)


def list_cases() -> list[dict]:
    return [
        {"case_id": cid, "company_name": s.get("company_name"), "scenario": s.get("scenario")}
        for cid, s in _CASES.items()
    ]
