from app.agents.base_agent import run_extraction
from app.schemas.common import ExtractionResult
from app.schemas.kyc import KYCData
from app.validation.rules import check_kyc

INSTRUCTIONS = """\
You are the KYC/Entity Agent in a credit underwriting pipeline.
You will receive a KYC Summary document with sections like ENTITY / BUSINESS DETAILS, PROPRIETOR / KYC DETAILS, ADDRESS VERIFICATION, and CREDIT BUREAU SNAPSHOT.

Extract EXACTLY these fields:

1. legal_name — the "Legal Name" of the entity, e.g. "M/S. Classic Motors". Look in section 1 "ENTITY / BUSINESS DETAILS".
2. cin — Corporate Identification Number if present; empty string "" for proprietorships (they have no CIN)
3. pan — PAN number of the proprietor or company (e.g. "BTZPA0997H"). Look in ENTITY DETAILS or PROPRIETOR DETAILS.
4. incorporation_date — GST Registration Date or business start date (format: YYYY-MM-DD). For proprietorships use the GST Registration Date.
5. entity_type — one of: "pvt_ltd", "llp", "partnership", "proprietorship", "public_ltd".
   Map: "Proprietorship" → "proprietorship", "Private Limited" → "pvt_ltd", "LLP" → "llp"
6. registered_address — the business/registered address. Look in "Registered / Business Address" field.
7. directors — list of proprietors/directors. For proprietorships, the proprietor is the single entry.
   Each item: { "name": "Full Name", "din": "DIN if available else empty string", "designation": "Proprietor or Director" }
8. kyc_doc_status — "complete" if all key documents (PAN, address, identity) are present; "incomplete" otherwise.
   Mark "complete" if PAN, address, and at least one identity proof (Aadhaar/Voter ID/DL) are present.

IMPORTANT:
- Do NOT return empty string for legal_name, pan, registered_address if they appear in the document.
- For proprietorships, cin should be empty string "".
- Always respond with a JSON object only — no markdown, no explanation.
"""


def run(raw_text: str) -> ExtractionResult:
    return run_extraction(
        source="kyc",
        schema_cls=KYCData,
        raw_text=raw_text,
        agent_instructions=INSTRUCTIONS,
        validator_fn=check_kyc,
    )
