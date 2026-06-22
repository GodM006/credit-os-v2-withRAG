from app.agents.base_agent import run_extraction
from app.schemas.banking import BankingData
from app.schemas.common import ExtractionResult
from app.validation.rules import check_banking

INSTRUCTIONS = """\
You are the Banking Agent in a credit underwriting pipeline.
You read raw bank statement text / Account Aggregator (AA) feed exports and
extract a clean structured summary: account details, total credits/debits,
average and minimum balance, cheque/ECS bounce count, and an inferred annual
turnover figure (annualise whatever period the statement covers).
Be conservative: if a figure isn't clearly stated, make the best reasonable
estimate from the numbers present and don't invent accounts that aren't mentioned.
"""


def run(raw_text: str) -> ExtractionResult:
    return run_extraction(
        source="banking",
        schema_cls=BankingData,
        raw_text=raw_text,
        agent_instructions=INSTRUCTIONS,
        validator_fn=check_banking,
    )
