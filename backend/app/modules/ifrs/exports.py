"""Exports reproduce immutable runs; they never recalculate or invent disclosures."""

import io
import json
from decimal import Decimal, localcontext
from html import escape

from app.modules.ifrs.review import presentation_lines, presented


def rows_for(run, released, reviewers=()):
    with localcontext() as precision:
        precision.prec = 48
        return _rows_for(run, released, reviewers)


def _rows_for(run, released, reviewers):
    data = run.results
    rows = [
        ["AUDITOS UAE", "Financial reporting package"],
        ["Release", "REVIEWED" if released else "DRAFT — HUMAN REVIEW REQUIRED"],
        ["Entity", data.get("entity", "Calculation schedule")],
        ["Period", f"{data.get('period_start', '')} to {data.get('period_end', '')}"],
        ["Currency", data.get("currency", "See approved assumptions")],
        ["Run ID", str(run.id)],
        ["SHA-256", run.sha256],
        ["Methodology", run.methodology_version],
        ["Prepared by (user ID)", str(run.created_by)],
        ["Prepared UTC", str(run.created_at)],
        [
            "Reviewed by (user IDs)",
            ", ".join(reviewers) if released else "Pending independent review",
        ],
        ["Scope", data.get("scope", "Limited-scope deterministic calculation")],
    ]
    precision = data.get("precision", 2)
    def amount(value):
        return presented(value, "assets", precision)

    for section in ["assets", "liabilities", "equity", "income", "expenses", "oci"]:
        lines = [r for r in presentation_lines(data) if r["section"] == section]
        if not lines:
            continue
        rows.append([section.upper(), "Current", "Comparative", "Note"])
        for line in lines:
            rows.append(
                [
                    line["label"],
                    line["display_current"],
                    line["display_comparative"] if data.get("comparative") else "Not supplied",
                    line.get("note", ""),
                ]
            )
        rows.append(
            [
                "Total " + section,
                amount(sum((Decimal(r["display_current"]) for r in lines), Decimal(0))),
                amount(sum((Decimal(r["display_comparative"]) for r in lines), Decimal(0)))
                if data.get("comparative")
                else "Not supplied",
                "Sum of displayed lines",
            ]
        )
    summaries = {
        "totals": [
            "assets",
            "liabilities",
            "equity",
            "profit",
            "oci",
            "total_comprehensive_income",
            "cash",
        ],
        "changes_in_equity": ["opening", "profit", "oci", "direct_equity_movements", "closing"],
        "cash_flow": [
            "opening",
            "profit",
            "noncash_adjustments",
            "working_capital",
            "operating",
            "investing",
            "financing",
            "exchange_effect",
            "closing",
            "source_cash",
            "difference",
        ],
    }
    for section, keys in summaries.items():
        values = data.get(section) or {}
        if not values:
            continue
        rows.append([section.replace("_", " ").upper(), "Current", "Comparative", "Basis"])
        for key in keys:
            if key in values:
                rows.append(
                    [
                        key.replace("_", " ").capitalize(),
                        amount(values[key]),
                        "See statement lines" if data.get("comparative") else "Not supplied",
                        "Rounded exact amount",
                    ]
                )
        if section == "cash_flow":
            for key in ("method", "policy"):
                if key in values:
                    rows.append([key.capitalize(), str(values[key])])
    if data.get("validation"):
        rows.append(["VALIDATION"])
        for check in data["validation"].get("checks", []):
            rows.append(
                [
                    check["code"].replace("_", " ").capitalize(),
                    "Passed" if check["passed"] else "Review required",
                    amount(check["difference"]) if "difference" in check else "",
                    ", ".join(str(v) for v in check.get("missing", [])),
                ]
            )
    for note in data.get("notes", []):
        rows.append(["NOTE " + note["reference"]])
        rows.append(["Disclosure", note["text"]])
        rows.append(["Note line", "Current", "Comparative", "Basis"])
        for line in note["lines"]:
            source = next(
                (r for r in data.get("lines", []) if r["line_code"] == line["code"]), None
            )
            rows.append(
                [
                    line["code"],
                    presented(line["current"], source["section"], precision)
                    if source
                    else amount(line["current"]),
                    (
                        presented(line["comparative"], source["section"], precision)
                        if source
                        else amount(line["comparative"])
                    )
                    if data.get("comparative")
                    else "Not supplied",
                    "Presentation signs" if source else "Source signs",
                ]
            )
    if data.get("review"):
        rows.append(["FINANCIAL STATEMENT REVIEW"])
        for issue in data["review"]["issues"]:
            rows.append(
                [
                    issue["severity"],
                    issue["location"],
                    issue["message"],
                    json.dumps(issue["evidence"]),
                ]
            )
    if not data.get("lines"):
        rows.append(["CALCULATION RESULTS"])
        for key, value in data.items():
            if not isinstance(value, (dict, list)):
                rows.append([key.replace("_", " "), str(value)])
    for key in ["schedule", "journal_proposals", "members", "eliminations", "acquisition_schedule"]:
        value = data.get(key)
        if value:
            rows.append([key.replace("_", " ").upper()])
            for index, item in enumerate(value if isinstance(value, list) else [value], 1):
                rows.append([str(index), json.dumps(item, ensure_ascii=False)])
    rows.append(
        ["Professional review", "No IFRS compliance certification is made by this software."]
    )
    return rows


def render(
    run,
    format,
    released=False,
    reviewers=(),
    rows_override=None,
    document_title="Financial reporting package",
):
    payload = {
        "id": str(run.id),
        "sha256": run.sha256,
        "methodology_version": run.methodology_version,
        "released": released,
        "prepared_by": str(run.created_by),
        "created_at": str(run.created_at),
        "reviewed_by": list(reviewers) if released else [],
        "inputs": run.inputs,
        "dependencies": run.dependencies,
        "results": run.results,
    }
    if format == "json":
        return json.dumps(payload, indent=2, ensure_ascii=False).encode(), "application/json"
    rows = rows_for(run, released, reviewers) if rows_override is None else rows_override
    output = io.BytesIO()
    if format == "xlsx":
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill

        wb = Workbook()
        ws = wb.active
        ws.title = "Financial package"
        for index, row in enumerate(rows, 1):
            # All imported narrative remains literal, including Excel formula prefixes.
            for col, value in enumerate(row, 1):
                cell = ws.cell(index, col)
                cell.value = str(value)
                cell.data_type = "s"
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        for cell in ws[1]:
            cell.font = Font(color="FFFFFF", bold=True)
            cell.fill = PatternFill("solid", fgColor="14263B")
        for letter, width in {"A": 40, "B": 80, "C": 25, "D": 20}.items():
            ws.column_dimensions[letter].width = width
        ws.freeze_panes = "B10"
        for name, content in [("Sources", run.dependencies), ("Immutable run", payload)]:
            sheet = wb.create_sheet(name)
            for index, line in enumerate(
                json.dumps(content, indent=2, ensure_ascii=False).splitlines(), 1
            ):
                sheet.cell(index, 1, line).data_type = "s"
            sheet.column_dimensions["A"].width = 120
        wb.save(output)
        return (
            output.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    if format == "docx":
        from docx import Document
        from docx.oxml import OxmlElement
        from docx.shared import Inches, Pt

        doc = Document()
        doc.sections[0].header.paragraphs[0].text = "AUDITOS UAE | " + document_title
        doc.styles["Normal"].font.size = Pt(10)
        doc.add_heading(document_title, 0)
        doc.add_paragraph("REVIEWED" if released else "DRAFT — HUMAN REVIEW REQUIRED")
        table = None
        for row in rows[2:]:
            if len(row) == 1:
                doc.add_heading(row[0], 1)
                table = None
            elif len(row) == 4:
                if table is None or row[1] == "Current":
                    table = doc.add_table(rows=0, cols=4)
                    table.style = "Light Shading Accent 1"
                cells = table.add_row().cells
                for cell, value in zip(cells, row):
                    cell.text = value
            else:
                doc.add_paragraph(" | ".join(row))
                table = None
        doc.add_heading("Source lineage", 1)
        doc.add_paragraph(json.dumps(run.dependencies, indent=2))
        doc.sections[0].footer.paragraphs[0].text = f"Immutable run {run.id} | {run.sha256[:16]}"
        field = OxmlElement("w:fldSimple")
        from docx.oxml.ns import qn

        field.set(qn("w:instr"), "PAGE")
        footer = doc.sections[0].footer.paragraphs[0]
        footer.add_run(" | Page ")
        footer._p.append(field)
        doc.sections[0].top_margin = Inches(0.7)
        doc.save(output)
        return (
            output.getvalue(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    if format == "pdf":
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        styles = getSampleStyleSheet()
        story = []
        for row in rows:
            if len(row) == 4:
                cells = [[Paragraph(escape(value), styles["BodyText"]) for value in row]]
                financial_table = Table(cells, colWidths=[260, 90, 90, 83])
                commands = [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#DFE5EE")),
                ]
                if row[1] == "Current":
                    commands.append(("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EDF2F8")))
                financial_table.setStyle(TableStyle(commands))
                story.append(financial_table)
            else:
                style = styles["Heading2"] if len(row) == 1 else styles["BodyText"]
                story.append(Paragraph(escape(" | ".join(row)).replace("\n", "<br/>"), style))
                if len(row) != 1:
                    story.append(Spacer(1, 7))
        story.append(Paragraph("Source lineage", styles["Heading2"]))
        for dep in run.dependencies:
            story.append(Paragraph(escape(json.dumps(dep)), styles["BodyText"]))

        def footer(canvas, doc):
            if not released:
                canvas.saveState()
                canvas.setFillColor(colors.Color(0.75, 0.78, 0.82, alpha=0.2))
                canvas.setFont("Helvetica-Bold", 64)
                canvas.translate(180, 330)
                canvas.rotate(40)
                canvas.drawString(0, 0, "DRAFT")
                canvas.restoreState()
            canvas.setFont("Helvetica", 8)
            canvas.drawString(36, 22, f"AuditOS UAE | {str(run.id)[:8]} | Page {doc.page}")

        SimpleDocTemplate(
            output, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=40
        ).build(story, onFirstPage=footer, onLaterPages=footer)
        return output.getvalue(), "application/pdf"
    raise ValueError("Unsupported format")
