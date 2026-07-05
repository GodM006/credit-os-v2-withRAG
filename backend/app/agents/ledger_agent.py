from app.agents.base_agent import run_extraction
from app.schemas.common import ExtractionResult
from app.schemas.ledger import LedgerData
from app.validation.rules import check_ledger

INSTRUCTIONS = """\
You are the Ledger/Invoice Agent in a credit underwriting pipeline.
You will receive a parsed sales ledger or purchase ledger, typically in tabular text form with columns like:
Invoice Date | Invoice No. | Customer / Buyer | GSTIN of Buyer | Taxable Value | Tax | Invoice Value | Category

Extract EXACTLY these fields:

1. period — the statement period mentioned in the header (e.g. "Jul-2025 to Dec-2025")
2. total_sales — extract the pre-computed Total Sales / Total Invoice Value from the summary box or ledger header (do NOT manually sum individual invoice rows).
   If sales and purchases are in separate sheets, use the reported total from the sales sheet.
3. total_purchases — extract the reported Total Purchases from the purchase ledger summary box if present; otherwise null.
4. debtor_days — if stated in a summary section, extract it; otherwise estimate as (outstanding_receivables / monthly_avg_sales * 30)
5. creditor_days — if stated, extract; otherwise null
6. top_debtor_concentration_pct — % of total sales to the single largest buyer (by Invoice Value sum per buyer).
   Compute: (buyer_with_max_sales / total_sales) * 100
7. overdue_receivables — any explicitly mentioned overdue/outstanding receivable amount; default 0 if not mentioned

CRITICAL for total_sales: Extract the reported Grand Total / Summary Total for sales. Do NOT attempt mental arithmetic addition across individual invoice rows.

Always respond with a JSON object only — no markdown, no explanation.
"""


def run(raw_text: str) -> ExtractionResult:
    return run_extraction(
        source="ledger",
        schema_cls=LedgerData,
        raw_text=raw_text,
        agent_instructions=INSTRUCTIONS,
        validator_fn=check_ledger,
    )
