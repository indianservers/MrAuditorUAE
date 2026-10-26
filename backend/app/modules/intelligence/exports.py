"""Exact source-value exports; human conclusions remain distinct from generated tables."""

import io
import json
from xml.sax.saxutils import escape


def render(event, format):
    if event["kind"] == "statutory-report":
        from app.modules.regulatory.report_exports import render as report_render

        return report_render(event, format)
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
        "Export timestamp": event.get("exported_at", "NOT_RECORDED"),
        "Source freshness at export": event.get("freshness", "NOT_EVALUATED"),
        "Export status": "STALE_HISTORICAL_RESULT_REQUIRES_RECALCULATION" if event.get("freshness") == "STALE" else "CURRENT_RETAINED_RESULT" if event.get("freshness") == "CURRENT" else "FRESHNESS_NOT_EVALUATED",
        "Prepared by": ", ".join(body.get("contributors", [])),
        "Reviewed by": body.get("reviewer"),
        "Generated result timestamp": event["created_at"],
        "Financial convention": "Exact Decimal strings; no audit opinion or evidence sufficiency inferred",
    }
    if format == "xlsx":
        metadata["XLSX text contract"] = "exact-text-with-continuations/1"
    if event["kind"] in {"workflow-source", "country-workflow"}:
        metadata.update(
            {
                "Workflow": body.get("workflow", body.get("table_type")),
                "Population completeness": body.get("population_completeness"),
                "Statutory calculation qualified": body.get(
                    "statutory_calculation_qualified", False
                ),
                "Professional conclusion": body.get("professional_conclusion", "NOT_DETERMINED"),
                "Workflow limitations": body.get("limitations", []),
            }
        )
    if body.get("box_comparison_scope", {}).get("mode") == "SELECTED_REQUIRED_BOXES":
        metadata["Comparison scope"] = (
            "Selected VAT201 boxes only: "
            + ", ".join(body["box_comparison_scope"]["required_boxes"])
            + ". Whole-return completeness is not determined."
        )
    if body.get("excluded_box_rows"):
        metadata["Excluded VAT box rows"] = (
            f"{len(body['excluded_box_rows'])} outside the selected box scope; full details are retained in the XLSX Excluded VAT boxes sheet and original source result"
        )
    if body.get("obligation_population_scope") == "ARREARS_ONLY_NOT_COMPLETE_MONTHLY_RETURN":
        metadata["Comparison scope"] = "Arrears only; regular monthly obligations, returns and payments are outside this comparison. Salary disbursement does not establish PF contribution payment."
    summary = {
        k: v
        for k, v in body.items()
        if k
        in {
            "totals",
            "totals_basis",
            "totals_by_currency",
            "control_comparison",
            "booking_date_review_count",
            "import_nil_scope",
            "document_series_contract",
            "document_series_scope",
            "document_series_totals",
            "document_series_controls",
            "count_unit",
            "bank_account_contract",
            "bank_account_evidence",
            "bank_account_scope",
            "bank_profile_references",
            "bank_authentication_status",
            "allocation_controls",
            "bank_consumption_manifest",
            "bank_consumption_review",
            "payment_scope",
            "source_totals",
            "destination_totals",
            "section",
            "sampling_method",
            "seed",
            "source_batch_id",
            "source_snapshot_id",
            "source_filename",
            "coverage",
            "adjusted_book_balance",
            "country_guidance",
            "source_roles",
            "exception_count",
            "blocked",
            "parameters",
            "nil_population",
            "nil_declarations",
            "execution_mode",
            "ml_execution_mode",
            "language_model_dependency",
            "calculation_engine",
            "total_ecl_by_currency",
            "count_bridges",
            "payroll_ledger_scope",
            "native_format",
            "native_metadata",
            "csv_mapping",
            "supporting_table_id",
            "supporting_table_metadata",
            "supporting_scope_assessment",
            "supporting_table_basis",
            "supporting_side",
            "supporting_balance_date",
            "supporting_amount_sign",
            "account_identity_verified",
            "native_controls_verified",
            "expected_total",
            "expected_total_complete",
            "expected_total_basis",
            "rule_document_binding",
            "rule_document_version_id",
            "reported_total",
            "currency",
            "withholding_role",
            "comparison_basis",
            "selected_current_totals",
            "assessment_contract_version",
            "box_comparison_scope",
            "vat201_layout",
            "invoice_evidence_scope",
        "outward_gst_scope",
            "excluded_box_controls",
            "included_box_controls",
        }
    }

    if isinstance(body.get("count_bridges"), list):
        summary["count_bridges"] = f"{len(body['count_bridges'])} bridge rows; complete original count details and individual movement links are retained in the XLSX Count date bridges and Inventory movement links sheets"
    if isinstance(body.get("inventory_quantity_controls"), list):
        summary["inventory_quantity_controls"] = f"{len(body['inventory_quantity_controls'])} controlled partitions; complete row and directional quantity controls are retained in the XLSX Inventory quantity controls sheet"

    if isinstance(body.get("transaction_dates"), list):
        summary["transaction_dates"] = f"{len(body['transaction_dates'])} retained transaction date records; complete detail is retained in the XLSX Bank transaction dates sheet"
    if isinstance(body.get("payroll_posting_links"), list):
        summary["payroll_posting_links"] = f"{len(body['payroll_posting_links'])} individual source posting links; complete detail is retained in the XLSX Payroll posting links sheet"

    def text(value):
        return (
            json.dumps(value, ensure_ascii=False, sort_keys=True)
            if isinstance(value, (dict, list))
            else ""
            if value is None
            else str(value)
        )

    native_metadata = body.get("native_metadata")
    message_controls = (
        native_metadata.get("message_controls", [])
        if body.get("native_format") == "swift-mt940" and isinstance(native_metadata, dict)
        else []
    )
    if message_controls:
        summary["native_metadata"] = {
            **body["native_metadata"],
            "message_controls": f"{len(message_controls)} message control records retained in the source result and full XLSX MT940 message controls sheet",
        }
    page_controls = (
        native_metadata.get("page_controls", [])
        if body.get("native_format") == "camt053" and isinstance(native_metadata, dict)
        else []
    )
    if page_controls:
        summary["native_metadata"] = {
            **body["native_metadata"],
            "page_controls": f"{len(page_controls)} page control records retained in the source result and full XLSX CAMT page controls sheet",
        }

    buffer = io.BytesIO()
    if format == "xlsx":
        from openpyxl import Workbook

        from app.modules.intelligence.xlsx_values import ExactTextWriter, XlsxValueLimitError

        workbook = Workbook(write_only=True)
        writer = ExactTextWriter(workbook, text)
        append = writer.append

        try:
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
            if body.get("workflow") == "party-balance-confirmations":
                links = workbook.create_sheet("Confirmation item links")
                documents = workbook.create_sheet("Confirmation documents")
                identity_fields = ["id", "account", "counterparty", "side", "currency"]
                append(links, ["result_row_id", *identity_fields[1:], "reply_scope_membership", "open_item_source_id"])
                append(documents, ["result_row_id", *identity_fields[1:], "confirmation_status", "request_basis", "scope_balance", "requested_amount", "document_role", "document_date", "evidence_version_id", "source_sha256", "reference", "contact_verified_declaration", "independent_receipt_declaration", "scope_assessment", "followup_kind", "followup_assessment", "evidence_status"])
                for position in body.get("rows", []):
                    if position.get("kind") != "party-confirmation":
                        continue
                    identity = [position.get(field) for field in identity_fields]
                    for identifier in position.get("open_item_source_ids", []):
                        membership = "FULL_BALANCE_SCOPE"
                        if position.get("confirmation_status") == "partially-received":
                            covered = position.get("covered_item_source_ids")
                            membership = "UNASSESSED_PARTIAL_SCOPE" if covered is None else "DECLARED_REPLY_COVERED" if identifier in covered else "NOT_REPLY_COVERED"
                        append(links, [*identity, membership, identifier])
                    evidence = position.get("confirmation_evidence") or {}
                    for prefix, date_field in (("request", "requested_on"), ("response", "responded_on"), ("followup", "followup_on")):
                        if evidence.get(prefix + "_evidence_version_id"):
                            append(documents, [*identity, position.get("confirmation_status"), evidence.get("request_basis"), evidence.get("scope_balance"), evidence.get("requested_amount"), prefix, evidence.get(date_field), evidence[prefix + "_evidence_version_id"], evidence[prefix + "_source_sha256"], evidence[prefix + "_reference"], evidence.get("contact_verified"), evidence.get("independently_received"), evidence.get("scope_assessment"), evidence.get("followup_kind") if prefix == "followup" else None, evidence.get("followup_assessment") if prefix == "followup" else None, "RETAINED_IDENTITY_ONLY"])
            if body.get("confirmation_coverage_links") is not None:
                coverage = workbook.create_sheet("Confirmation coverage links")
                fields = ["source_row_id", "confirmation_source_row_id", "item_id", "as_of", "account", "counterparty", "side", "currency", "book_amount", "evidence_reference"]
                append(coverage, fields)
                for link in body["confirmation_coverage_links"]:
                    append(coverage, [link.get(field) for field in fields])
            if body.get("workflow") == "sanctions-name-review":
                candidates = workbook.create_sheet("Screening candidates")
                candidate_fields = ["source_id", "list_subject_id", "list_name", "list_version", "published_on", "evidence_reference", "name_similarity"]
                append(candidates, ["subject_id", "subject_name", "subject_evidence_reference", "candidate_retention", *candidate_fields])
                for subject in body.get("rows", []):
                    incomplete = subject.get("candidate_preview_truncated") or (subject.get("candidate_count") is not None and subject["candidate_count"] != len(subject.get("candidates", [])))
                    retained = "LEGACY_TRUNCATED" if incomplete else body.get("candidate_retention_contract", "LEGACY_UNQUALIFIED")
                    for candidate in subject.get("candidates", []):
                        append(candidates, [subject.get("id"), subject.get("subject_name"), subject.get("subject_evidence_reference"), retained, *[candidate.get(key) for key in candidate_fields]])
            if body.get("transaction_dates") is not None:
                dates = workbook.create_sheet("Bank transaction dates")
                date_fields = ["source_role", "source_row_id", "transaction_date", "bank_booking_date", "bank_value_date", "bank_date_basis", "booking_date_review_required"]
                append(dates, date_fields)
                for record in body["transaction_dates"]:
                    append(dates, [record.get(key) for key in date_fields])
            if body.get("payroll_posting_links") is not None:
                posting_links = workbook.create_sheet("Payroll posting links")
                posting_fields = list(dict.fromkeys(key for row in body["payroll_posting_links"] for key in row))
                append(posting_links, posting_fields)
                for link in body["payroll_posting_links"]:
                    append(posting_links, [link.get(key) for key in posting_fields])
            if body.get("inventory_quantity_controls") is not None:
                controls = workbook.create_sheet("Inventory quantity controls")
                fields = ["site", "sku", "lot", "uom", "currency", "expected_rows", "positive_quantity", "negative_quantity"]
                append(controls, fields)
                for control in body["inventory_quantity_controls"]:
                    append(controls, [control.get(key) for key in fields])
            if body.get("purchase_quantity_controls") is not None:
                controls = workbook.create_sheet("Purchase quantity controls")
                fields = ["order_id", "line_reference", "vendor", "currency", "uom", "document_type", "expected_rows", "quantity"]
                append(controls, fields)
                for control in body["purchase_quantity_controls"]:
                    append(controls, [control.get(key) for key in fields])
            if body.get("count_bridges") is not None:
                bridges = workbook.create_sheet("Count date bridges")
                links = workbook.create_sheet("Inventory movement links")
                bridge_keys = list(dict.fromkeys(key for bridge in body["count_bridges"] for key in bridge if key != "movement_source_ids"))
                append(bridges, bridge_keys)
                append(links, ["count_source_id", "movement_source_id", "site", "sku", "lot", "uom", "currency"])
                for bridge in body["count_bridges"]:
                    append(bridges, [bridge.get(key) for key in bridge_keys])
                    for movement_id in bridge.get("movement_source_ids", []):
                        append(links, [bridge["count_source_id"], movement_id, *[bridge.get(key) for key in ["site", "sku", "lot", "uom", "currency"]]])
            if body.get("excluded_box_rows"):
                excluded = workbook.create_sheet("Excluded VAT boxes")
                excluded_keys = list(
                    dict.fromkeys(key for row in body["excluded_box_rows"] for key in row)
                )
                append(excluded, excluded_keys)
                for row in body["excluded_box_rows"]:
                    append(excluded, [row.get(key) for key in excluded_keys])
            if message_controls:
                messages = workbook.create_sheet("MT940 message controls")
                message_keys = list(
                    dict.fromkeys(key for message in message_controls for key in message)
                )
                append(messages, message_keys)
                for message in message_controls:
                    append(messages, [message.get(key) for key in message_keys])
            if page_controls:
                pages = workbook.create_sheet("CAMT page controls")
                page_keys = list(dict.fromkeys(key for page in page_controls for key in page))
                append(pages, page_keys)
                for page in page_controls:
                    append(pages, [page.get(key) for key in page_keys])
            cash_manifest = body.get("bank_consumption_manifest")
            if isinstance(cash_manifest, dict) and isinstance(cash_manifest.get("rows"), list):
                cash = workbook.create_sheet("Bank cash claims")
                cash_keys = list(dict.fromkeys(["bank_source_row_id", "account", "account_basis", "currency", "capacity", "allocated", "source_sha256", "cash_key", "economic_key", "origin_key", *[key for claim in cash_manifest["rows"] for key in claim]]))
                from openpyxl.utils import get_column_letter

                cash.freeze_panes = "A2"
                for index, key in enumerate(cash_keys, 1):
                    cash.column_dimensions[get_column_letter(index)].width = 68 if key.endswith("key") or key.endswith("sha256") else 42 if key in {"capacity", "allocated"} else 36 if key in {"account", "account_basis"} else max(24, len(key) + 2)
                append(cash, cash_keys)
                for claim in cash_manifest["rows"]:
                    append(cash, [claim.get(key) for key in cash_keys])
            receipts = workbook.create_sheet("Dependency receipts")
            for dep in event["dependencies"]:
                append(receipts, [dep["type"], dep])
            if writer.long_values:
                append(cover, ["Oversized cells", f"{len(writer.long_values)} exact values retained in ordered parts on Long values; source sheet/cell and UTF-8 SHA-256 identify each original value"])
            writer.finish()
            workbook.save(buffer)
            return (
                buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        except XlsxValueLimitError:
            # Public save closes streaming XML writers and removes their temp
            # files. This partial cleanup archive is discarded, never returned.
            from contextlib import suppress

            with suppress(Exception):
                workbook.save(io.BytesIO())
            raise
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
