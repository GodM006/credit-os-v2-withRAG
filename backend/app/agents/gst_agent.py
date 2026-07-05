from app.agents.base_agent import run_extraction
from app.schemas.common import ExtractionResult
from app.schemas.gst import GSTData
from app.validation.rules import check_gst

INSTRUCTIONS = """\
You are the Tax/GST Agent in a credit underwriting pipeline.
You will receive JSON or text from a GST portal export containing entity profile and GSTR-1/GSTR-3B filing compliance records.

Extract EXACTLY these fields:

1. gstin — the 15-character GST Identification Number (look in "entity_profile" > "gstin")
2. legal_name — the registered legal business name (look in "entity_profile" > "legal_name")
3. registration_date — date_of_registration in the entity_profile (format: YYYY-MM-DD)
4. filing_frequency — infer "monthly" or "quarterly" from the compliance records (monthly if GSTR-3B appears monthly)
5. last_filed_period — the most recent tax_period in the compliance list, e.g. "Dec-2025"
6. filing_status — "regular" if returns are filed consistently, "defaulter" if there are large gaps or many late filings
7. gstr3b_annual_turnover — extract pre-computed annual turnover from "gstr3b_overall_summary", "annual_summary", or "business_summary" (do NOT manually sum individual monthly rows).
8. gstr1_annual_turnover — extract from "gstr1_overall_summary" or "annual_summary" (if available, else same as gstr3b).
9. vintage_months — number of months from registration_date to today (approx, integer)
10. late_filings_last_12m — count of compliance rows where status is "Filed Late" in the last 12 months

IMPORTANT: Do NOT return null for gstin, legal_name, registration_date, last_filed_period if they are present in the document.
Do NOT attempt mental arithmetic addition across monthly compliance rows — always look for reported total/summary fields.
If turnover data is not in the compliance table but the Financials mention revenue, use that.
Always respond with a JSON object only — no markdown, no explanation.
"""


def run(raw_text: str) -> ExtractionResult:
    return run_extraction(
        source="gst",
        schema_cls=GSTData,
        raw_text=raw_text,
        agent_instructions=INSTRUCTIONS,
        validator_fn=check_gst,
    )
