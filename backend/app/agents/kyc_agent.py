from app.agents.base_agent import run_extraction
from app.schemas.common import ExtractionResult
from app.schemas.kyc import KYCData
from app.validation.rules import check_kyc

INSTRUCTIONS = """\
You are the KYC/Entity Agent in a credit underwriting pipeline.
You read raw company registration, director, ownership, and KYC document
text and extract: legal name, CIN, PAN, incorporation date, entity type,
registered address, the list of directors (name, DIN, designation), and the
overall KYC document completeness status.
"""


def run(raw_text: str) -> ExtractionResult:
    return run_extraction(
        source="kyc",
        schema_cls=KYCData,
        raw_text=raw_text,
        agent_instructions=INSTRUCTIONS,
        validator_fn=check_kyc,
    )
