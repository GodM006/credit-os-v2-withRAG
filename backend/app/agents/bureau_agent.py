from app.agents.base_agent import run_extraction
from app.schemas.bureau import BureauData
from app.schemas.common import ExtractionResult
from app.validation.rules import check_bureau

INSTRUCTIONS = """\
You are the Bureau Agent in a credit underwriting pipeline.
You read raw commercial or personal credit bureau report text and extract:
bureau score, total exposure, overdue amount, counts of accounts at 30/60/90+
days-past-due, hard enquiries in the last 6 months, written-off accounts, and
active account count. If the report doesn't state a field explicitly, use 0
for counts/amounts rather than guessing a non-zero number.
"""


def run(raw_text: str) -> ExtractionResult:
    return run_extraction(
        source="bureau",
        schema_cls=BureauData,
        raw_text=raw_text,
        agent_instructions=INSTRUCTIONS,
        validator_fn=check_bureau,
    )
