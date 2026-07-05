"""
Generates the Credit Appraisal Memorandum as a PDF using ReportLab Platypus.
Returns a BytesIO buffer ready to stream as a download.
"""
from __future__ import annotations

import io
from typing import Any, Dict, List, Tuple

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Colours ──────────────────────────────────────────────────────────────────
NAVY    = colors.HexColor("#1A2A4A")
TEAL    = colors.HexColor("#0D7C7C")
LIGHT   = colors.HexColor("#E8F4F4")
ALT     = colors.HexColor("#F2F6FA")
HBG     = colors.HexColor("#1A2A4A")
KBG     = colors.HexColor("#EEF2F8")
PASS_C  = colors.HexColor("#1A7A40")
FAIL_C  = colors.HexColor("#C02020")
WARN_C  = colors.HexColor("#B86E00")
BORDER  = colors.HexColor("#C0C8D8")
MUTED   = colors.HexColor("#708090")
WHITE   = colors.white

W = A4[0] - 2 * cm  # content width


# ── Style helpers ─────────────────────────────────────────────────────────────
def _styles():
    base = getSampleStyleSheet()
    defs = {
        "Title": ParagraphStyle("Title", parent=base["Normal"],
            fontSize=18, textColor=NAVY, alignment=1, spaceAfter=4,
            fontName="Helvetica-Bold"),
        "Subtitle": ParagraphStyle("Subtitle", parent=base["Normal"],
            fontSize=11, textColor=TEAL, alignment=1, spaceAfter=4,
            fontName="Helvetica"),
        "CompanyName": ParagraphStyle("CompanyName", parent=base["Normal"],
            fontSize=13, textColor=NAVY, alignment=1, spaceAfter=4,
            fontName="Helvetica-Bold"),
        "Meta": ParagraphStyle("Meta", parent=base["Normal"],
            fontSize=8, textColor=MUTED, alignment=1, spaceAfter=2),
        "SectionHead": ParagraphStyle("SectionHead", parent=base["Normal"],
            fontSize=11, textColor=NAVY, spaceAfter=6, spaceBefore=10,
            fontName="Helvetica-Bold", borderPadding=(0, 0, 2, 0)),
        "SubHead": ParagraphStyle("SubHead", parent=base["Normal"],
            fontSize=9, textColor=NAVY, spaceAfter=3, spaceBefore=6,
            fontName="Helvetica-Bold"),
        "Body": ParagraphStyle("Body", parent=base["Normal"],
            fontSize=9, textColor=colors.HexColor("#303840"),
            spaceAfter=5, leading=13),
        "FraudHigh": ParagraphStyle("FraudHigh", parent=base["Normal"],
            fontSize=10, textColor=FAIL_C, fontName="Helvetica-Bold", spaceAfter=4),
        "FraudMed": ParagraphStyle("FraudMed", parent=base["Normal"],
            fontSize=10, textColor=WARN_C, fontName="Helvetica-Bold", spaceAfter=4),
        "FraudLow": ParagraphStyle("FraudLow", parent=base["Normal"],
            fontSize=10, textColor=PASS_C, fontName="Helvetica-Bold", spaceAfter=4),
        "DecisionClear": ParagraphStyle("DecisionClear", parent=base["Normal"],
            fontSize=10, textColor=PASS_C, fontName="Helvetica-Bold", spaceAfter=4),
        "DecisionWarn": ParagraphStyle("DecisionWarn", parent=base["Normal"],
            fontSize=10, textColor=WARN_C, fontName="Helvetica-Bold", spaceAfter=4),
        "DecisionFail": ParagraphStyle("DecisionFail", parent=base["Normal"],
            fontSize=10, textColor=FAIL_C, fontName="Helvetica-Bold", spaceAfter=4),
        "Footer": ParagraphStyle("Footer", parent=base["Normal"],
            fontSize=7.5, textColor=MUTED, alignment=1, spaceAfter=0),
    }
    return defs


def _kv_table(rows: List[Tuple[str, str]]) -> Table:
    data = [[Paragraph(f"<b>{k}</b>", ParagraphStyle("kk", fontSize=8.5, textColor=NAVY)),
             Paragraph(str(v), ParagraphStyle("kv", fontSize=8.5))]
            for k, v in rows]
    t = Table(data, colWidths=[6.5 * cm, 11 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), KBG),
        ("BACKGROUND", (1, 0), (1, -1), WHITE),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def _data_table(headers: List[str], rows: List[Tuple], col_w_cm: List[float]) -> Table:
    header_row = [Paragraph(f"<b>{h}</b>",
                  ParagraphStyle("hh", fontSize=8, textColor=WHITE))
                  for h in headers]
    data_rows = [[Paragraph(str(c), ParagraphStyle("dd", fontSize=8))
                  for c in row] for row in rows]
    data = [header_row] + data_rows
    t = Table(data, colWidths=[x * cm for x in col_w_cm])
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), HBG),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]
    for i in range(1, len(rows) + 1):
        bg = ALT if i % 2 == 1 else WHITE
        style.append(("BACKGROUND", (0, i), (-1, i), bg))
    t.setStyle(TableStyle(style))
    return t


def _hr() -> HRFlowable:
    return HRFlowable(width="100%", thickness=1, color=TEAL, spaceAfter=6, spaceBefore=6)


def generate_cam_pdf(cam: Dict[str, Any], analyst_narrative: str) -> io.BytesIO:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            topMargin=2 * cm, bottomMargin=2 * cm,
                            leftMargin=2 * cm, rightMargin=2 * cm,
                            title=f"CAM - {cam['meta']['company_name']}")
    s = _styles()
    story = []

    meta = cam["meta"]

    # ── Cover ──────────────────────────────────────────────────────────────
    story += [
        Spacer(1, 1.5 * cm),
        Paragraph("CREDIT APPRAISAL MEMORANDUM", s["Title"]),
        Paragraph("Working Capital Facility", s["Subtitle"]),
        Spacer(1, 0.3 * cm),
        Paragraph(meta["company_name"], s["CompanyName"]),
        Spacer(1, 0.3 * cm),
        Paragraph(f"Case ID: {meta['case_id']}  &nbsp;&nbsp;|&nbsp;&nbsp;  Generated: {meta['generated_at']}", s["Meta"]),
        Paragraph(f"Prepared by: {meta['prepared_by']}", s["Meta"]),
        PageBreak(),
    ]

    def section(title, content_items):
        story.append(_hr())
        story.append(Paragraph(title, s["SectionHead"]))
        story.extend(content_items)

    # ── S1 ─────────────────────────────────────────────────────────────────
    section(cam["s1_basic_info"]["title"], [_kv_table(cam["s1_basic_info"]["rows"])])

    # ── S2 ─────────────────────────────────────────────────────────────────
    section(cam["s2_credit_requirement"]["title"], [_kv_table(cam["s2_credit_requirement"]["rows"])])

    # ── S3 ─────────────────────────────────────────────────────────────────
    s3 = cam["s3_financial_analysis"]
    section(s3["title"], [
        Paragraph(f"Period: {s3['period']}   |   Audited: {s3['is_audited']}", s["Body"]),
        Paragraph("P&amp;L Summary", s["SubHead"]),
        _kv_table(s3["pnl_rows"]),
        Spacer(1, 0.2 * cm),
        Paragraph("Balance Sheet Summary", s["SubHead"]),
        _kv_table(s3["bs_rows"]),
        Spacer(1, 0.2 * cm),
        Paragraph("Ledger Analysis", s["SubHead"]),
        _kv_table(s3["ledger_rows"]),
    ])

    # ── S4 ─────────────────────────────────────────────────────────────────
    section(cam["s4_banking"]["title"], [_kv_table(cam["s4_banking"]["rows"])])

    # ── S5 ─────────────────────────────────────────────────────────────────
    section(cam["s5_bureau"]["title"], [_kv_table(cam["s5_bureau"]["rows"])])

    # ── S6 ─────────────────────────────────────────────────────────────────
    section(cam["s6_gst"]["title"], [_kv_table(cam["s6_gst"]["rows"])])

    # ── S7 ─────────────────────────────────────────────────────────────────
    s7 = cam["s7_triangulation"]
    s7_items = []
    if s7["pairwise_rows"]:
        s7_items += [
            Paragraph("Pairwise Turnover Comparison", s["SubHead"]),
            _data_table(
                ["Comparison", "Source A", "Source B", "Variance", "Trust Wt"],
                s7["pairwise_rows"], [5.5, 2.8, 2.8, 2.0, 2.2]),
            Spacer(1, 0.2 * cm),
        ]
    if s7["source_weights"]:
        s7_items += [
            Paragraph("Aggregated Source Trust Weights", s["SubHead"]),
            _data_table(["Source", "Trust Weight"], s7["source_weights"], [5, 3]),
            Spacer(1, 0.2 * cm),
        ]
    s7_items += [
        Paragraph("Effective Metrics", s["SubHead"]),
        _kv_table(s7["effective_rows"]),
    ]
    section(s7["title"], s7_items)

    # ── S8 ─────────────────────────────────────────────────────────────────
    s8 = cam["s8_fraud"]
    fraud_style_map = {"LOW": s["FraudLow"], "MEDIUM": s["FraudMed"], "HIGH": s["FraudHigh"]}
    s8_items = [
        Paragraph(f"Overall Fraud Risk: {s8['fraud_risk']}", fraud_style_map.get(s8["fraud_risk"], s["FraudMed"])),
    ]
    if s8["signals"]:
        s8_items += [
            Paragraph("Fraud Signals", s["SubHead"]),
            _data_table(["Signal Type", "Severity", "Detail"], s8["signals"], [4, 2, 9.3]),
        ]
    else:
        s8_items.append(Paragraph("No fraud signals detected.", s["Body"]))
    if s8["contradictions"]:
        s8_items += [
            Spacer(1, 0.2 * cm),
            Paragraph("Contradictions", s["SubHead"]),
            _data_table(["Pair", "Variance", "Detail"], s8["contradictions"], [4, 2, 9.3]),
        ]
    section(s8["title"], s8_items)

    # ── S9 ─────────────────────────────────────────────────────────────────
    s9 = cam["s9_policy"]
    dec_style = {"CLEAR": s["DecisionClear"], "DEVIATION REQUIRED": s["DecisionWarn"],
                 "POLICY REJECT": s["DecisionFail"]}.get(s9["decision"], s["DecisionWarn"])
    s9_items = [
        Paragraph(f"Policy Decision: {s9['decision']}   |   Pass Rate: {s9['pass_rate']}   |   Deviation Flag: {s9['deviation_flag']}", dec_style),
    ]
    if s9["rule_rows"]:
        s9_items += [
            _data_table(["Rule", "Result", "Actual", "Threshold", "Note"],
                        s9["rule_rows"], [5.5, 1.5, 2.5, 2.0, 3.8]),
        ]
    section(s9["title"], s9_items)

    # ── S10 ────────────────────────────────────────────────────────────────
    section(cam["s10_ml"]["title"], [_kv_table(cam["s10_ml"]["rows"])])

    # ── S11 ────────────────────────────────────────────────────────────────
    s11 = cam["s11_limit"]
    s11_items = []
    if s11["constraint_rows"]:
        s11_items += [
            _data_table(["Constraint", "Ceiling Amount"], s11["constraint_rows"], [11, 4.3]),
            Spacer(1, 0.3 * cm),
        ]
    s11_items.append(_kv_table([
        ("Recommended Sanction Limit", s11["recommended_limit"]),
        ("Binding Constraint", s11["binding_constraint"]),
        ("Note", s11["note"]),
    ]))
    section(s11["title"], s11_items)

    # ── S12 Analyst Observations ───────────────────────────────────────────
    story.append(PageBreak())
    story.append(_hr())
    story.append(Paragraph("SECTION 12 — ANALYST OBSERVATIONS", s["SectionHead"]))
    story.append(Paragraph(
        "The following narrative was generated by the Credit Decisioning OS AI pipeline "
        "based on verified data from the underwriting process. All figures referenced below "
        "are drawn from extracted and reconciled source data.",
        ParagraphStyle("note", fontSize=8, textColor=MUTED, spaceAfter=8)))
    for para in (analyst_narrative or "").split("\n\n"):
        para = para.strip()
        if para:
            story.append(Paragraph(para, s["Body"]))
            story.append(Spacer(1, 0.15 * cm))

    # ── Footer ─────────────────────────────────────────────────────────────
    story += [
        Spacer(1, 1 * cm),
        _hr(),
        Paragraph(f"CONFIDENTIAL — FOR INTERNAL CREDIT COMMITTEE USE ONLY   |   {meta['prepared_by']}", s["Footer"]),
    ]

    doc.build(story)
    buf.seek(0)
    return buf
