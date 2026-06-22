from app.agents.base_agent import run_extraction
from app.schemas.common import ExtractionResult
from app.schemas.financials import FinancialsData
from app.validation.rules import check_financials

INSTRUCTIONS = """\
You are the Financials Agent in a credit underwriting pipeline.
You read raw P&L, balance sheet, and audited financial statement text and
extract: reporting period, whether the statements are audited, revenue,
EBITDA, net profit, total assets, total liabilities, net worth, and the
debt/equity ratio (compute it from liabilities and net worth if not stated
directly).
"""


def run(raw_text: str) -> ExtractionResult:
    return run_extraction(
        source="financials",
        schema_cls=FinancialsData,
        raw_text=raw_text,
        agent_instructions=INSTRUCTIONS,
        validator_fn=check_financials,
    )
