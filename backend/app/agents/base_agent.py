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
import re
import time
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


def _eval_math_expression(expr_str: str) -> str:
    expr = expr_str.strip()
    # Handle JS/ternary operators cond ? a : b
    if "?" in expr and ":" in expr:
        try:
            parts = expr.split("?")
            cond = parts[0].strip()
            rest = parts[1].split(":")
            val_true = rest[0].strip()
            val_false = rest[1].strip()
            cond_py = cond.replace("null", "None").replace("true", "True").replace("false", "False")
            val_true_py = val_true.replace("null", "None").replace("true", "True").replace("false", "False")
            val_false_py = val_false.replace("null", "None").replace("true", "True").replace("false", "False")
            
            # Restrict eval context to safe basic mathematics
            cond_val = eval(cond_py, {"__builtins__": None}, {})
            if cond_val:
                return str(eval(val_true_py, {"__builtins__": None}, {}))
            else:
                return "null" if val_false_py == "None" else str(eval(val_false_py, {"__builtins__": None}, {}))
        except Exception:
            match = re.search(r"[\d.]+", expr)
            return match.group(0) if match else "null"

    # Handle basic mathematical formulas (addition, subtraction, multiplication, division)
    expr = expr.replace("null", "None").replace("true", "True").replace("false", "False")
    try:
        val = eval(expr, {"__builtins__": None}, {})
        if val is None:
            return "null"
        return str(val)
    except Exception:
        match = re.search(r"[\d.]+", expr)
        return match.group(0) if match else "null"


def _repair_json(text: str) -> str:
    """Attempt to repair common JSON malformations from smaller LLMs.

    Handles: trailing commas, single quotes, unquoted string values,
    unquoted mathematical expressions (e.g. 1000 + 200), truncated output,
    and nested {"value": X} objects from schema-confused models.

    Order of operations matters: nested-object flattening MUST run before the
    math-expression regex, otherwise strings like "FY 2025-26" (which contain '-')
    inside wrapper objects get mangled.
    """
    # Step 1: Remove trailing commas before } or ] (safe to do first)
    text = re.sub(r",\s*([}\]])", r"\1", text)

    # Step 2: Try to parse as valid JSON immediately.
    # If it parses, check for nested {"value": X} wrappers and flatten them.
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            flattened = {}
            changed = False
            for k, v in parsed.items():
                if isinstance(v, dict):
                    for wrapper_key in ("value", "extracted", "amount", "number", "data"):
                        if wrapper_key in v and len(v) == 1:
                            flattened[k] = v[wrapper_key]
                            changed = True
                            break
                    else:
                        flattened[k] = v
                else:
                    flattened[k] = v
            if changed:
                return json.dumps(flattened)
        return text
    except json.JSONDecodeError:
        pass

    # Step 3: Apply math-expression / ternary repair for unquoted numeric expressions
    def replacer(match):
        key = match.group(1)
        val_str = match.group(2).strip()
        # Leave already-valid JSON scalars alone
        if (val_str.startswith('"') and val_str.endswith('"')) or val_str in ("true", "false", "null"):
            return match.group(0)
        # Only evaluate if it looks like a math expression (not a plain word/string)
        if re.search(r"[\d]", val_str) and any(op in val_str for op in ("+", "*", "/")):
            evaluated = _eval_math_expression(val_str)
            return f'"{key}": {evaluated}'
        return match.group(0)

    try:
        text = re.sub(r'"([^"]+)"\s*:\s*([^,\n}]+)', replacer, text)
    except Exception as e:
        logger.error("JSON math expression repair failed: %s", e)

    # Step 4: Try again after math repair
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass

    # Step 5: Replace single quotes with double quotes
    try:
        repaired = text.replace("'", '"')
        json.loads(repaired)
        return repaired
    except json.JSONDecodeError:
        pass

    # Step 6: Close unclosed braces/brackets (truncated output)
    open_braces = text.count("{") - text.count("}")
    open_brackets = text.count("[") - text.count("]")
    if open_braces > 0 or open_brackets > 0:
        last_complete = max(text.rfind(","), text.rfind("{"), text.rfind("["))
        if last_complete > 0 and text.rfind(",") == last_complete:
            repaired = text[:last_complete]
        else:
            repaired = text
        repaired += "]" * open_brackets + "}" * open_braces
        repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
        try:
            json.loads(repaired)
            return repaired
        except json.JSONDecodeError:
            pass

    return text  # return original if nothing worked



def _simplify_schema(schema_cls: Type[T]) -> str:
    """Convert a Pydantic JSON schema into a clean, flat {field: type} string.

    Pydantic's full schema includes noisy metadata (anyOf, title, description)
    that causes smaller LLMs to parrot the schema definition instead of extracting
    data. This function emits a compact, human-readable format like:
        period: string
        revenue: number
        total_assets: number or null
    """
    raw = schema_cls.model_json_schema()
    props = raw.get("properties", {})
    lines = []
    for field_name, field_def in props.items():
        # Handle anyOf (Optional types)
        if "anyOf" in field_def:
            types = []
            for sub in field_def["anyOf"]:
                t = sub.get("type", "any")
                if t != "null":
                    types.append(t)
            type_str = " or ".join(types) + " or null" if types else "any or null"
        else:
            type_str = field_def.get("type", "any")
        lines.append(f"  {field_name}: {type_str}")
    return "{\n" + "\n".join(lines) + "\n}"


def _parse_retry_after(error_msg: str) -> float:
    """
    Extract the wait time from a Groq 429 error message.
    Supports 'Xs' (seconds) and 'Xm Y.Zs' (minutes + seconds) formats.
    Returns a float seconds value, capped at 60s.
    """
    # Format: '39m9.216s' — minutes and seconds
    match = re.search(r"try again in\s+([\d]+)m([\d.]+)s", error_msg)
    if match:
        total = float(match.group(1)) * 60 + float(match.group(2))
        return min(total + 1.0, 60.0)  # cap at 60s
    # Format: '12.5s' — plain seconds
    match = re.search(r"try again in\s+([\d.]+)s", error_msg)
    if match:
        return min(float(match.group(1)) + 1.0, 60.0)
    return 30.0


def _is_rate_limit(error_msg: str) -> bool:
    return "429" in error_msg or "rate_limit" in error_msg.lower() or "limit_exceeded" in error_msg.lower()


def _is_daily_limit(error_msg: str) -> bool:
    """Detect Groq tokens-per-day exhaustion (TPD). These have very long retry times
    (many minutes) and should trigger an immediate model fallback rather than a wait."""
    msg_lower = error_msg.lower()
    return (
        "tokens per day" in msg_lower
        or "tpd" in msg_lower
        or ("tokens" in msg_lower and "limit" in msg_lower and "day" in msg_lower)
        # Long wait (>90s) is also a strong signal of daily quota exhaustion
        or bool(re.search(r"try again in\s+\d+m", error_msg))
    )


def extract_structured(
    schema_cls: Type[T],
    raw_text: str,
    agent_instructions: str,
    max_retries: int | None = None,
) -> Tuple[T | None, float, list[ValidationIssue], int, str]:
    """
    Returns (parsed_model_or_None, confidence, issues, attempts_used, model_name).

    Rate-limit strategy:
      1. Primary model (llama-3.3-70b-versatile) hits 429
         → wait retry_after seconds, then switch to fallback
      2. Fallback model (llama-3.1-8b-instant) hits 429
         → wait retry_after seconds, then try fallback once more
      3. If still failing, record error and abort
    """
    max_retries = settings.GROQ_MAX_RETRIES if max_retries is None else max_retries
    model_name = settings.GROQ_MODEL
    llm = get_llm(model=model_name)
    # Use a simplified schema that small models understand better.
    # Full Pydantic schemas (with anyOf, title, description) confuse 8B models
    # into parroting the schema definition rather than extracting data.
    schema_simple = _simplify_schema(schema_cls)
    # Build a concrete example from actual field names so the model knows exactly
    # what flat JSON to produce.
    props = schema_cls.model_json_schema().get("properties", {})
    example_fields = list(props.keys())[:3]
    example_lines = []
    for f in example_fields:
        example_lines.append(f'  "{f}": <extracted value or null>')
    example_str = "{\n" + ",\n".join(example_lines) + "\n}"

    system_prompt = (
        f"{agent_instructions}\n\n"
        "TASK: Extract values from the document into a flat JSON object.\n"
        "OUTPUT FORMAT RULES (CRITICAL):\n"
        "  1. Output a single JSON object with ONLY the field names listed in the schema below as keys.\n"
        "  2. Each value must be the EXTRACTED DATA (a string, number, boolean, or null).\n"
        "  3. Do NOT nest objects. Do NOT output {\"value\": ...} wrappers.\n"
        "  4. Do NOT output the schema definition. Do NOT use \"properties\", \"type\", \"anyOf\", \"title\".\n"
        "  5. For missing fields use null (not the string 'null', not 'N/A').\n"
        "  6. No markdown fences, no explanation — raw JSON only.\n"
        f"EXAMPLE OUTPUT FORMAT (using your actual field names):\n{example_str}\n\n"
        "FIELD SCHEMA (field_name: type):\n"
        f"{schema_simple}"
    )

    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": raw_text},
    ]

    issues: list[ValidationIssue] = []
    last_error: str | None = None
    last_raw_content = ""
    # Track which models we've tried, to avoid switching twice
    fallback_used = False

    for attempt in range(1, max_retries + 2):  # at least 1 attempt, then retries
        try:
            response = llm.invoke(messages)
            last_raw_content = response.content if isinstance(response.content, str) else str(response.content)
            cleaned = _strip_code_fences(last_raw_content)
            cleaned = _repair_json(cleaned)
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
                        "No markdown, no explanation. "
                        "For missing/unknown values use null, not the string 'Not Provided'."
                    ),
                }
            )

        except Exception as e:  # network/API errors etc.
            last_error = str(e)

            if _is_rate_limit(last_error):
                wait_secs = _parse_retry_after(last_error)

                if not fallback_used:
                    if _is_daily_limit(last_error):
                        # Daily TPD exhausted — no point waiting; immediately switch to
                        # the fallback model which has a separate daily quota.
                        logger.warning(
                            "Daily token limit (TPD) exhausted on '%s'. Immediately switching to fallback '%s'.",
                            model_name, settings.GROQ_FALLBACK_MODEL,
                        )
                    elif attempt >= max_retries + 1:
                        # Last attempt on primary — switch to fallback model.
                        logger.warning(
                            "Rate limit hit on '%s' (attempt %d). Waiting %.1fs then falling back to '%s'...",
                            model_name, attempt, wait_secs, settings.GROQ_FALLBACK_MODEL,
                        )
                        time.sleep(wait_secs)
                    else:
                        # Per-minute rate limit — wait and retry on primary model.
                        logger.warning(
                            "Rate limit hit on '%s' (attempt %d). Waiting %.1fs then retrying...",
                            model_name, attempt, wait_secs,
                        )
                        time.sleep(wait_secs)
                        continue
                    model_name = settings.GROQ_FALLBACK_MODEL
                    llm = get_llm(model=model_name)
                    fallback_used = True
                    continue
                else:
                    # Fallback model also rate-limited — short wait and retry once more.
                    logger.warning(
                        "Rate limit also hit on fallback '%s' (attempt %d). Waiting %.1fs...",
                        model_name, attempt, min(wait_secs, 30.0),
                    )
                    time.sleep(min(wait_secs, 30.0))
                    continue

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
