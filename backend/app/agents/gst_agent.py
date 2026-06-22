from app.agents.base_agent import run_extraction
from app.schemas.common import ExtractionResult
from app.schemas.gst import GSTData
from app.validation.rules import check_gst

INSTRUCTIONS = """\
You are the Tax/GST Agent in a credit underwriting pipeline.
You read raw GST registration details and GSTR-1 / GSTR-3B filing summaries
(India) and extract: GSTIN, legal name, registration date, filing frequency
and status, annual turnover as per GSTR-3B and GSTR-1 separately (they can
differ - report both, don't average them), vintage in months, and count of
late filings in the last 12 months if mentioned.
"""


def run(raw_text: str) -> ExtractionResult:
    return run_extraction(
        source="gst",
        schema_cls=GSTData,
        raw_text=raw_text,
        agent_instructions=INSTRUCTIONS,
        validator_fn=check_gst,
    )
