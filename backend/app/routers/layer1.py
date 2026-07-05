from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, File, UploadFile
from pydantic import BaseModel

from app import store
from app.graph.layer1_graph import layer1_app
from app.state import new_case_state
from app.utils.parsers import parse_file

router = APIRouter(prefix="/api/layer1", tags=["layer1"])


@router.post("/cases/upload")
async def upload_case_files(
    consumer_cibil: UploadFile = File(None),
    commercial_cibil: UploadFile = File(None),
    bank_statement_1: UploadFile = File(None),
    bank_statement_2: UploadFile = File(None),
    gst_json: UploadFile = File(None),
    financials: UploadFile = File(None),
    ledger: UploadFile = File(None),
    kyc: UploadFile = File(None),
):
    """Create a case from uploaded documents (PDF CIBILs, Excel statements, GST JSON, etc.)."""
    raw_docs = {
        "banking": "",
        "gst": "",
        "bureau": "",
        "financials": "",
        "ledger": "",
        "kyc": "",
    }
    
    uploaded_files_summary = []

    # 1. Parse KYC if present
    company_name = "Uploaded Case"
    if kyc:
        content = await kyc.read()
        parsed_text = parse_file(kyc.filename, content)
        raw_docs["kyc"] = parsed_text
        uploaded_files_summary.append(f"kyc: {kyc.filename}")
        
        # Heuristic: look for Company Name or Legal Name
        for line in parsed_text.split("\n"):
            if "Legal Name" in line or "Company Name" in line or "Entity:" in line:
                parts = line.split(":")
                if len(parts) > 1 and parts[1].strip():
                    company_name = parts[1].strip()
                    break

    # 2. Parse GST JSON if present
    if gst_json:
        content = await gst_json.read()
        parsed_text = parse_file(gst_json.filename, content)
        raw_docs["gst"] = parsed_text
        uploaded_files_summary.append(f"gst: {gst_json.filename}")
        
        # Try to parse company name if still default
        if company_name == "Uploaded Case":
            import json
            try:
                data = json.loads(parsed_text)
                if isinstance(data, dict):
                    company_name = data.get("legal_name") or data.get("company_name") or "Uploaded Case"
            except Exception:
                pass

    # 3. Parse CIBIL bureau reports (Consumer and/or Commercial)
    bureau_texts = []
    if consumer_cibil:
        content = await consumer_cibil.read()
        bureau_texts.append(f"=== CONSUMER CIBIL REPORT ===\n" + parse_file(consumer_cibil.filename, content))
        uploaded_files_summary.append(f"consumer_cibil: {consumer_cibil.filename}")
    if commercial_cibil:
        content = await commercial_cibil.read()
        bureau_texts.append(f"=== COMMERCIAL CIBIL REPORT ===\n" + parse_file(commercial_cibil.filename, content))
        uploaded_files_summary.append(f"commercial_cibil: {commercial_cibil.filename}")
    if bureau_texts:
        raw_docs["bureau"] = "\n\n".join(bureau_texts)

    # 4. Parse Bank Statements (1 and/or 2)
    bank_texts = []
    if bank_statement_1:
        content = await bank_statement_1.read()
        bank_texts.append(f"=== BANK STATEMENT 1 ===\n" + parse_file(bank_statement_1.filename, content))
        uploaded_files_summary.append(f"bank_statement_1: {bank_statement_1.filename}")
    if bank_statement_2:
        content = await bank_statement_2.read()
        bank_texts.append(f"=== BANK STATEMENT 2 ===\n" + parse_file(bank_statement_2.filename, content))
        uploaded_files_summary.append(f"bank_statement_2: {bank_statement_2.filename}")
    if bank_texts:
        raw_docs["banking"] = "\n\n".join(bank_texts)

    # 5. Parse financials
    if financials:
        content = await financials.read()
        raw_docs["financials"] = parse_file(financials.filename, content)
        uploaded_files_summary.append(f"financials: {financials.filename}")

    # 6. Parse ledger
    if ledger:
        content = await ledger.read()
        raw_docs["ledger"] = parse_file(ledger.filename, content)
        uploaded_files_summary.append(f"ledger: {ledger.filename}")

    # Validate that we got at least some content
    has_content = any(len(text) > 0 for text in raw_docs.values())
    if not has_content:
        raise HTTPException(status_code=400, detail="No files uploaded or files were empty.")

    case_id = str(uuid.uuid4())[:8]
    
    state = new_case_state(
        case_id=case_id,
        raw_docs=raw_docs,
        company_name=company_name,
        scenario="uploaded",
    )
    
    state["audit_trail"].append({
        "layer": 1,
        "agent": "file_uploader",
        "detail": {"uploaded_files": uploaded_files_summary},
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    
    store.save_case(case_id, dict(state))
    return state


@router.get("/cases")
def list_cases():
    return store.list_cases()


@router.get("/cases/{case_id}")
def get_case(case_id: str):
    state = store.get_case(case_id)
    if state is None:
        raise HTTPException(status_code=404, detail="case not found")
    return state


@router.post("/cases/{case_id}/run")
def run_case(case_id: str):
    """Run the Layer 1 LangGraph pipeline (all 6 agents, in parallel) on a stored case."""
    state = store.get_case(case_id)
    if state is None:
        raise HTTPException(status_code=404, detail="case not found")

    result_state = layer1_app.invoke(state)
    store.save_case(case_id, dict(result_state))
    return result_state
