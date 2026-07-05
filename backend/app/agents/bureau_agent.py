from app.agents.base_agent import run_extraction
from app.schemas.bureau import BureauData
from app.schemas.common import ExtractionResult
from app.validation.rules import check_bureau

INSTRUCTIONS = """\
You are the Bureau Agent in a credit underwriting pipeline.
You will receive raw text from a CIBIL, CRIF, or Experian credit bureau report.
The input may contain BOTH a commercial report (CIBIL MSME Rank / CMR) AND a personal report (Consumer CIR).

If BOTH are present in the text, you must AGGREGATE and COMBINE the details of both reports:
1. entity_type — Set to "commercial" if a commercial report is present in the text, otherwise "personal".
2. bureau_score — Prioritize the Commercial MSME Rank score (translated to numeric 300-900). If commercial is not present, use the personal score.
   - For CMR (Commercial): Map CMR-1→900, CMR-2→800, CMR-3→720, CMR-4→650, CMR-5→580, CMR-6→520, CMR-7→460, CMR-8→400, CMR-9→350, CMR-10→300.
   - For Personal (Consumer): Use the raw credit score (e.g. CREDITVISION score like 739).
3. total_exposure — extract the pre-computed Total Exposure / Total Sanctioned Limit / Total Outstanding Balance reported in the CREDIT SUMMARY or ACCOUNT SUMMARY boxes at the top of the report (do NOT manually sum individual loan accounts down in the details).
4. overdue_amount — extract the pre-computed Total Overdue Amount reported in the summary section (do NOT manually add individual overdue accounts).
5. dpd_30 — SUM of the count of 30-59 DPD accounts from both reports.
6. dpd_60 — SUM of the count of 60-89 DPD accounts from both reports.
7. dpd_90_plus — SUM of the count of 90+ DPD accounts from both reports.
8. enquiries_last_6m — SUM of the hard credit enquiries in the last 6 months from both reports.
9. written_off_accounts — SUM of the written-off or settled accounts from both reports.
10. active_accounts — SUM of open/active credit accounts from both reports.

IMPORTANT:
- Do NOT attempt mental arithmetic addition of individual loan balances — always look for reported Total Exposure / Total Balance in summary tables.
- Use 0 for counts and amounts that are explicitly zero or not mentioned (do NOT return null for integer fields).
- For consumer CIR: look at ACCOUNT INFORMATION summary for DPD counts and balances.
- For commercial: look at the CREDIT SUMMARY and CREDIT FACILITY summary sections.
- Always respond with a JSON object only — no markdown, no explanation.
"""


def run(raw_text: str) -> ExtractionResult:
    return run_extraction(
        source="bureau",
        schema_cls=BureauData,
        raw_text=raw_text,
        agent_instructions=INSTRUCTIONS,
        validator_fn=check_bureau,
    )
