from app.agents.base_agent import run_extraction
from app.schemas.common import ExtractionResult
from app.schemas.ledger import LedgerData
from app.validation.rules import check_ledger

INSTRUCTIONS = """\
You are the Ledger/Invoice Agent in a credit underwriting pipeline.
You read raw sales ledger, purchase ledger, and invoice summary text and
extract: reporting period, total sales, total purchases, average debtor days,
average creditor days, the % of total receivables owed by the single largest
debtor (concentration risk), and overdue receivables.
"""


def run(raw_text: str) -> ExtractionResult:
    return run_extraction(
        source="ledger",
        schema_cls=LedgerData,
        raw_text=raw_text,
        agent_instructions=INSTRUCTIONS,
        validator_fn=check_ledger,
    )
