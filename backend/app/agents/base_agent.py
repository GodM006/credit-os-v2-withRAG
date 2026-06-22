"""
Shared "extraction engine" used by all six Layer 1 agents.

Each agent is conceptually: (raw_text, instructions, schema) -> ExtractionResult.
This module does the actual LLM call (via Groq), strict Pydantic validation,
and a bounded retry loop that feeds validation errors back to the model so it
can self-correct -- this is what "context-aware agents get it right" means in
practice: instead of regex/OCR-only parsing, the model reads messy/synthetic
text and is forced to emit something that satisfies a strict schema.
"""
from __future__ import annotations

import json
import logging
from typing import Tuple, Type, TypeVar

from langchain_groq import ChatGroq
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.schemas.common import ExtractionResult, ValidationIssue
from app.validation.rules import status_from_issues

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def get_llm(model: str | None = None, temperature: float | None = None) -> ChatGroq:
    return ChatGroq(
        model=model or settings.GROQ_MODEL,
        api_key=settings.GROQ_API_KEY,
        temperature=temperature if temperature is not None else settings.GROQ_TEMPERATURE,
    )


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        # parts[0] is empty, parts[1] is the fenced block (maybe prefixed with 'json')
        body = parts[1] if len(parts) > 1 else text
        if body.lower().startswith("json"):
            body = body[4:]
        text = body.strip()
    return text


def extract_structured(
    schema_cls: Type[T],
    raw_text: str,
    agent_instructions: str,
    max_retries: int | None = None,
) -> Tuple[T | None, float, list[ValidationIssue], int, str]:
    """
    Returns (parsed_model_or_None, confidence, issues, attempts_used, model_name).
    """
    max_retries = settings.GROQ_MAX_RETRIES if max_retries is None else max_retries
    model_name = settings.GROQ_MODEL
    llm = get_llm(model=model_name)
    schema_json = json.dumps(schema_cls.model_json_schema(), indent=2)

    system_prompt = (
        f"{agent_instructions}\n\n"
        "Read the document below and extract the requested fields.\n"
        "Respond with ONLY a single valid JSON object matching this JSON Schema exactly "
        "(no markdown fences, no commentary, no trailing text):\n\n"
        f"{schema_json}"
    )

    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": raw_text},
    ]

    issues: list[ValidationIssue] = []
    last_error: str | None = None
    last_raw_content = ""

    for attempt in range(1, max_retries + 2):  # at least 1 attempt, then retries
        try:
            response = llm.invoke(messages)
            last_raw_content = response.content if isinstance(response.content, str) else str(response.content)
            cleaned = _strip_code_fences(last_raw_content)
            data = json.loads(cleaned)
            parsed = schema_cls.model_validate(data)
            confidence = round(max(0.5, 1.0 - 0.15 * (attempt - 1)), 2)
            return parsed, confidence, issues, attempt, model_name

        except (json.JSONDecodeError, ValidationError) as e:
            last_error = str(e)
            issues.append(
                ValidationIssue(
                    field="_root",
                    message=f"Attempt {attempt} failed: {last_error[:300]}",
                    severity="warning",
                )
            )
            messages.append({"role": "assistant", "content": last_raw_content})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"That response was invalid: {last_error[:500]}\n"
                        "Return corrected JSON only, matching the schema exactly. "
                        "No markdown, no explanation."
                    ),
                }
            )
        except Exception as e:  # network/API errors etc.
            last_error = str(e)
            issues.append(
                ValidationIssue(field="_root", message=f"LLM call failed: {last_error[:300]}", severity="error")
            )
            break

    issues.append(
        ValidationIssue(
            field="_root",
            message=f"Extraction failed after exhausting retries: {last_error}",
            severity="error",
        )
    )
    return None, 0.0, issues, max_retries + 1, model_name


def run_extraction(
    source: str,
    schema_cls: Type[T],
    raw_text: str,
    agent_instructions: str,
    validator_fn,
) -> ExtractionResult:
    """
    Full agent run: LLM extraction -> Pydantic validation (with retries) ->
    business-rule checks -> a single ExtractionResult ready to drop into
    AppState.source_jsons[source].
    """
    parsed, confidence, llm_issues, attempts, model_name = extract_structured(
        schema_cls=schema_cls, raw_text=raw_text, agent_instructions=agent_instructions
    )

    rule_issues: list[ValidationIssue] = validator_fn(parsed) if parsed is not None else []
    all_issues = llm_issues + rule_issues
    status = status_from_issues(all_issues) if parsed is not None else "invalid"

    return ExtractionResult(
        source=source,
        data=parsed,
        confidence=confidence if parsed is not None else 0.0,
        validation_status=status,
        issues=all_issues,
        raw_excerpt=raw_text[:280],
        model_used=model_name,
        attempts=attempts,
    )
