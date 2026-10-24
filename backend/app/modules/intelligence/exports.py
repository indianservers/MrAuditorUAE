"""Exact source-value exports; human conclusions remain distinct from generated tables."""

import io
import json
from xml.sax.saxutils import escape


def render(event, format):
    body = event["body"]
    rows = (
        body.get("rows")
        or body.get("items")
        or body.get("suggestions")
        or body.get("matches")
        or []
    )
    metadata = {
        "Firm": event.get("firm_name", ""),
        "Reference": event["id"],
        "Result kind": event["kind"],
        "Version": event["version"],
        "SHA-256": event["sha256"],
        "Country": body.get("country"),
        "Framework": body.get("reporting_framework"),
        "Review status": body.get("review_status", "UNVERIFIED"),
        "Prepared by": ", ".join(body.get("contributors", [])),
        "Reviewed by": body.get("reviewer"),
        "Generated result timestamp": event["created_at"],
        "Financial convention": "Exact Decimal strings; no audit opinion or evidence sufficiency inferred",
    }
    summary = {
        k: v
        for k, v in body.items()
        if k
        in {
            "totals",
            "totals_by_currency",
            "control_comparison",
            "source_totals",
            "destination_totals",
            "section",
            "sampling_method",
            "seed",
            "source_batch_id",
            "source_snapshot_id",
            "source_filename",
        }
    }

    def text(value):
        return (
            json.dumps(value, ensure_ascii=False, sort_keys=True)
            if isinstance(value, (dict, list))
            else ""
            if value is None
            else str(value)
        )

    buffer = io.BytesIO()
    if format == "xlsx":
        from openpyxl import Workbook
        from openpyxl.cell import WriteOnlyCell

        workbook = Workbook(write_only=True)

        def append(sheet, values):
            cells = []
            for value in values:
                cell = WriteOnlyCell(sheet, value=text(value))
                cell.data_type = "s"
                cells.append(cell)
            sheet.append(cells)

        cover = workbook.create_sheet("Source and review")
        for key, value in metadata.items():
            append(cover, [key, value])
        for key, value in summary.items():
            append(cover, [key, value])
        source = workbook.create_sheet("Rows")
        keys = list(dict.fromkeys(key for row in rows for key in row))
        append(source, keys)
        for row in rows:
            append(source, [row.get(key) for key in keys])
        receipts = workbook.create_sheet("Dependency receipts")
        for dep in event["dependencies"]:
            append(receipts, [dep["type"], dep])
        workbook.save(buffer)
        return (
            buffer.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    if format == "docx":
        from docx import Document

        document = Document()
        document.add_heading("Mr Auditor — reviewable audit schedule", 0)
        for key, value in metadata.items():
            document.add_paragraph(f"{key}: {text(value)}")
        document.add_heading("System-generated calculations", 1)
        for key, value in summary.items():
            document.add_paragraph(f"{key}: {text(value)}")
        for index, row in enumerate(rows[:500], 1):
            document.add_paragraph(f"{index}. {text(row)}")
        if len(rows) > 500:
            document.add_paragraph(
                f"Bounded document preview: first 500 of {len(rows)} rows. The XLSX export includes the full result population."
            )
        document.add_heading("Source receipts", 1)
        for dep in event["dependencies"]:
            document.add_paragraph(text(dep))
        document.save(buffer)
        return (
            buffer.getvalue(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    styles = getSampleStyleSheet()
    story = [Paragraph("Mr Auditor — reviewable audit schedule", styles["Title"])]
    for key, value in {**metadata, **summary}.items():
        story.extend([Paragraph(escape(f"{key}: {text(value)}"), styles["BodyText"]), Spacer(1, 6)])
    story.append(Paragraph("System-generated source rows", styles["Heading2"]))
    for index, row in enumerate(rows[:500], 1):
        story.extend([Paragraph(escape(f"{index}. {text(row)}"), styles["BodyText"]), Spacer(1, 6)])
    if len(rows) > 500:
        story.append(
            Paragraph(
                f"First 500 of {len(rows)} rows. Use the full XLSX export for the complete result.",
                styles["BodyText"],
            )
        )
    story.append(Paragraph("Dependency receipts", styles["Heading2"]))
    for dep in event["dependencies"]:
        story.append(Paragraph(escape(text(dep)), styles["BodyText"]))
    SimpleDocTemplate(buffer).build(story)
    return buffer.getvalue(), "application/pdf"
