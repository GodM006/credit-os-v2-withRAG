from app.agents.base_agent import run_extraction
from app.schemas.common import ExtractionResult
from app.schemas.financials import FinancialsData
from app.validation.rules import check_financials

INSTRUCTIONS = """\
You are the Financials Agent in a credit underwriting pipeline.
You will receive a P&L Statement and/or Balance Sheet in tabular text form. Rows have:
Particulars | FY 2024-25 | FY 2025-26 (Prov.) | YoY Growth %

Extract the MOST RECENT year's figures (FY 2025-26 column if present, otherwise FY 2024-25). Extract EXACTLY:

1. period — the financial year label, e.g. "FY 2025-26"
2. is_audited — true ONLY if the document explicitly says "Audited"; false if it says "Provisional" or "Prov."
3. revenue — the "Total Revenue from Operations" or "Sales" row value (largest income line)
4. ebitda — the "EBITDA" row value
5. net_profit — the "Profit After Tax (PAT)" or "Net Profit" row value
6. total_assets — from balance sheet "Total Assets" row; null if no balance sheet provided
7. total_liabilities — from balance sheet "Total Liabilities" row; null if not present
8. net_worth — from balance sheet "Net Worth" or "Equity" row; null if not present
9. debt_equity_ratio — compute as total_liabilities / net_worth if both available; null otherwise

STRICT OUTPUT FORMAT (MANDATORY):
- Return a SINGLE flat JSON object. ALL values must be numbers, strings, booleans, or null.
- Do NOT wrap values in {"value": ...} — output the number/string directly.
- Do NOT output the schema definition. Do NOT include keys like "properties", "anyOf", "type".
- Numbers must be plain numbers, e.g. 51715277 NOT "51,71,5277" NOT {"amount": 51715277}.
- Missing/not-present fields: use null (not "null", not "N/A", not 0).
- No markdown, no explanation — raw JSON only.

EXAMPLE CORRECT OUTPUT (when only P&L is present, no balance sheet):
{
  "period": "FY 2025-26",
  "is_audited": false,
  "revenue": 51715277,
  "ebitda": 5318005,
  "net_profit": 4342422,
  "total_assets": null,
  "total_liabilities": null,
  "net_worth": null,
  "debt_equity_ratio": null
}
"""


def run(raw_text: str) -> ExtractionResult:
    return run_extraction(
        source="financials",
        schema_cls=FinancialsData,
        raw_text=raw_text,
        agent_instructions=INSTRUCTIONS,
        validator_fn=check_financials,
    )
