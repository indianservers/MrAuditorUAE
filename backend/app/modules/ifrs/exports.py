"""Exports reproduce immutable runs; they never recalculate or invent disclosures."""

import io
import json
from decimal import ROUND_HALF_UP, Decimal
from html import escape


def rows_for(run, released, reviewers=()):
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
    quantum = Decimal(1).scaleb(-precision)

    def amount(value):
        rounded = Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP)
        return str(abs(rounded) if rounded == 0 else rounded)

    for section in ["assets", "liabilities", "equity", "income", "expenses", "oci"]:
        lines = [r for r in data.get("lines", []) if r["section"] == section]
        if not lines:
            continue
        rows.append([section.upper(), "Current", "Comparative", "Note"])
        for line in lines:
            sign = -1 if section in {"liabilities", "equity", "income", "oci"} else 1
            rows.append(
                [
                    line["label"],
                    amount(Decimal(line["current"]) * sign),
                    amount(Decimal(line.get("comparative", "0")) * sign)
                    if data.get("comparative")
                    else "Not supplied",
                    line.get("note", ""),
                ]
            )
    for section in ["totals", "changes_in_equity", "cash_flow", "validation"]:
        rows.append([section.replace("_", " ").upper()])
        for key, value in (data.get(section) or {}).items():
            rows.append(
                [
                    key,
                    json.dumps(value, ensure_ascii=False)
                    if isinstance(value, (dict, list))
                    else str(value),
                ]
            )
    for note in data.get("notes", []):
        rows.append(["Note " + note["reference"], note["text"]])
        rows.append(["Note line", "Current", "Comparative", "Basis"])
        for line in note["lines"]:
            rows.append(
                [
                    line["code"],
                    amount(line["current"]),
                    amount(line["comparative"]) if data.get("comparative") else "Not supplied",
                    "Source signs",
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
