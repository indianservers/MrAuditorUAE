"""Seed the owned disposable workflow database for browser verification only.

All documents are synthetic. Malware scanning and broker dispatch are explicit
in-process test doubles during fixture preparation, never server configuration.
"""

import asyncio
import hashlib
import io
import json
import os
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


async def main():
    from check_utf8_sources import ensure_utf8

    ensure_utf8()
    from app.core.config import settings
    from app.core.operations_contracts import implementation_hash

    implementation = implementation_hash()

    if (
        settings().environment != "test"
        or not settings().database_url.endswith("/auditos_country_workflows_test")
        or os.getenv("INTEGRATION_TESTS") != "1"
    ):
        raise SystemExit("Only the owned disposable country workflow test database is allowed")
    import pytest

    from tests.integration.test_platform import environment
    from tests.phase4.test_workflows import actor, create, grant, setup
    from tests.qa_crud.test_country_workflows import (
        bank_payload,
        decision,
        double_boundaries,
        execute,
        source,
    )
    from tests.unit.country_workflow_cases import document, return_box, transaction
    from tests.unit.native_source_examples import CAMT, SIF, SIF_FILENAME
    from tests.unit.test_india_ecr_source import ECR
    from tests.unit.test_india_gstr2b_source import payload as gstr2b_payload
    from tests.unit.test_india_invoice_source import invoice
    from tests.unit.test_payroll_rule_workflow import pf_fixture

    fixture = environment.__wrapped__()
    client = await anext(fixture)
    patch = pytest.MonkeyPatch()
    try:
        double_boundaries(patch)
        h, opts, eid, _base = await setup(client)
        book = await source(client, h, eid, [transaction()], "SYNTHETIC UAE cashbook")
        statement = await source(
            client,
            h,
            eid,
            [transaction(id="S1", amount="95")],
            "SYNTHETIC UAE bank",
            totals={"AED": "95"},
        )
        result = await execute(
            client,
            h,
            eid,
            "country-workflow",
            bank_payload(book, statement, statement_closing="95"),
        )
        vb = await source(
            client,
            h,
            eid,
            [return_box(id="B1")],
            "SYNTHETIC UAE VAT register boxes",
            "return-boxes",
            {"AED": "5"},
        )
        vr = await source(
            client,
            h,
            eid,
            [return_box(id="R1", tax="4")],
            "SYNTHETIC UAE VAT201 boxes",
            "return-boxes",
            {"AED": "4"},
        )
        vat_result = await execute(
            client,
            h,
            eid,
            "country-workflow",
            {
                "workflow": "uae-vat-return",
                "source_ids": {"books": vb["id"], "return": vr["id"]},
                "as_of": "2026-06-30",
                "title": "SYNTHETIC UAE VAT201 box bridge",
                "rationale": "Synthetic independently prepared book allocations and return boxes",
                "required_boxes": ["1:DXB"],
            },
        )
        e = await client.post(
            "/api/v1/entities",
            headers=h,
            json={
                "client_id": opts["client_id"],
                "name": "SYNTHETIC Indian entity",
                "country": "IN",
                "jurisdiction": "Synthetic test only",
                "functional_currency": "INR",
                "presentation_currency": "INR",
            },
        )
        assert e.status_code == 201, e.text
        p = await client.post(
            "/api/v1/financial-periods",
            headers=h,
            json={
                "entity_id": e.json()["id"],
                "start_date": "2026-04-01",
                "end_date": "2027-03-31",
            },
        )
        assert p.status_code == 201, p.text
        engagement = await client.post(
            "/api/v1/engagements",
            headers=h,
            json={
                "entity_id": e.json()["id"],
                "period_id": p.json()["id"],
                "name": "SYNTHETIC India workflow pilot",
                "engagement_type": "External Audit",
            },
        )
        assert engagement.status_code == 201, engagement.text
        india = engagement.json()["id"]
        d = document(currency="INR", component="CGST")
        a = await source(
            client,
            h,
            india,
            [d],
            "SYNTHETIC Indian purchase register",
            "tax-documents",
            {"INR": "5"},
        )
        b = await source(
            client,
            h,
            india,
            [document(id="R1", currency="INR", component="CGST", tax="4")],
            "SYNTHETIC Indian return schedule",
            "tax-documents",
            {"INR": "4"},
        )
        gst = await execute(
            client,
            h,
            india,
            "country-workflow",
            {
                "workflow": "india-gst",
                "source_ids": {"books": a["id"], "return": b["id"]},
                "as_of": "2026-06-30",
                "tax_year_start": "2026-04-01",
                "title": "SYNTHETIC India GST review",
                "rationale": "Synthetic independent canonical return and purchase schedules",
            },
        )

        async def native_file(engagement_id, filename, content, media):
            audit = f"/api/v1/engagements/{engagement_id}/audit"
            record = await create(
                client,
                h,
                audit,
                "evidence",
                {"category": "Other", "retain_until": "2036-12-31"},
            )
            uploaded = await client.post(
                audit + "/evidence-files/" + record["id"],
                headers=h,
                files={"file": (filename, content, media)},
            )
            assert uploaded.status_code == 201, uploaded.text
            return uploaded.json()["id"]

        camt_evidence = await native_file(eid, "SYNTHETIC-native-camt.xml", CAMT, "application/xml")
        wps_evidence = await native_file(eid, SIF_FILENAME, SIF, "text/csv")
        from datetime import datetime

        from openpyxl import Workbook

        from tests.unit.test_workflow_csv_mapping import SPLIT

        mapped_evidence = await native_file(
            eid, "SYNTHETIC-browser-split-bank.csv", SPLIT, "text/csv"
        )
        supporting_reviewer = await actor(
            h, "Firm Administrator", "browser-supporting-table-reviewer"
        )
        await grant(client, h, f"/api/v1/engagements/{eid}/audit", supporting_reviewer)
        supporting_ids = {}
        xlsx_ids = {}
        for kind in ("bank", "open-items"):
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Selected"
            if kind == "bank":
                sheet.append(["reference", "currency", "amount", "date", "account_code"])
                sheet.append(["REF-1", "AED", 100.25, datetime(2026, 6, 30), "BANK-1"])
                sheet.append(["REF-2", "AED", -5, datetime(2026, 6, 30), "BANK-1"])
            else:
                sheet.append(
                    [
                        "reference",
                        "currency",
                        "open_amount",
                        "counterparty",
                        "document_type",
                        "document_date",
                        "due_date",
                        "account_code",
                    ]
                )
                sheet.append(
                    [
                        "INV-1",
                        "AED",
                        -100,
                        "SYNTHETIC-SUPPLIER",
                        "invoice",
                        datetime(2026, 6, 1),
                        datetime(2026, 6, 30),
                        "AP-1",
                    ]
                )
                sheet.append(
                    [
                        "CN-1",
                        "AED",
                        20,
                        "SYNTHETIC-SUPPLIER",
                        "credit-note",
                        datetime(2026, 6, 5),
                        datetime(2026, 6, 30),
                        "AP-1",
                    ]
                )
            workbook.create_sheet("Other")
            buffer = io.BytesIO()
            workbook.save(buffer)
            workbook.close()
            xlsx_ids[kind] = await native_file(
                eid,
                f"SYNTHETIC-browser-{kind}.xlsx",
                buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            prepared = await execute(
                client,
                h,
                eid,
                "source-table",
                {
                    "evidence_version_id": xlsx_ids[kind],
                    "table_kind": kind,
                    "worksheet": "Selected",
                },
            )
            approved = await decision(client, supporting_reviewer[0], eid, prepared)
            assert approved.status_code == 201, approved.text
            supporting_ids[kind] = approved.json()["id"]
        extended_books = await source(
            client,
            h,
            eid,
            [
                transaction(id="BOOK-1", reference="REF-1", amount="100.25", date="2026-06-30"),
                transaction(id="BOOK-2", reference="REF-2", amount="-5", date="2026-06-30"),
            ],
            "SYNTHETIC extended independent cashbook",
            totals={"AED": "95.25"},
        )
        payable_controls = await source(
            client,
            h,
            eid,
            [
                {
                    "id": "AP-CONTROL",
                    "account": "AP-1",
                    "side": "payable",
                    "currency": "AED",
                    "as_of": "2026-06-30",
                    "amount": "80",
                }
            ],
            "SYNTHETIC independent payable control",
            "balance-controls",
            {"AED": "80"},
        )
        india_evidence = await native_file(
            india,
            "SYNTHETIC-native-inv01.json",
            json.dumps(invoice()).encode(),
            "application/json",
        )
        ecr_evidence = await native_file(india, "SYNTHETIC-monthly-ecr.txt", ECR, "text/plain")
        gstr2b_evidence = await native_file(
            india,
            "SYNTHETIC-gstr2b.json",
            json.dumps(gstr2b_payload()).encode(),
            "application/json",
        )
        gstr2b_books = await source(
            client,
            h,
            india,
            [
                document(
                    registration="27ABCDE5678G1Z8",
                    counterparty="29ABCDE1234F1Z5",
                    reference="SYNTHETIC-1",
                    date="2026-06-15",
                    currency="INR",
                    component="IGST",
                    tax="18",
                )
            ],
            "SYNTHETIC GSTR-2B independent book register",
            "tax-documents",
            {"INR": "18"},
        )
        legal_bytes = b"%PDF-1.4\nSYNTHETIC PAYROLL RULE EVIDENCE ONLY\n%%EOF"
        legal_id = await native_file(
            india, "SYNTHETIC-payroll-rules.pdf", legal_bytes, "application/pdf"
        )
        bases, rules, _ = pf_fixture()
        for rule in rules:
            rule.update(
                source_evidence_version_id=legal_id,
                source_sha256=hashlib.sha256(legal_bytes).hexdigest(),
            )
        payroll_bases = await source(
            client,
            h,
            india,
            bases,
            "SYNTHETIC assessed contribution bases",
            "payroll-bases",
            {"INR": "60000"},
        )
        payroll_rules = await source(
            client,
            h,
            india,
            rules,
            "SYNTHETIC reviewed contribution rules",
            "payroll-rules",
            {},
        )
        rule_reviewer = await actor(h, "Firm Administrator", "country-payroll-rule-reviewer")
        await grant(client, h, f"/api/v1/engagements/{india}/audit", rule_reviewer)
        reviewed_rules = await decision(client, rule_reviewer[0], india, payroll_rules)
        assert reviewed_rules.status_code == 201, reviewed_rules.text
        pf_evidence = await native_file(
            india,
            "SYNTHETIC-first-member-ecr.txt",
            ECR.splitlines()[0] + b"\n",
            "text/plain",
        )
        payroll_reported = await execute(
            client,
            h,
            india,
            "workflow-source",
            {
                "evidence_version_id": pf_evidence,
                "file_format": "india-epfo-ecr",
                "table_type": "obligations",
                "employer_registration": "EPFO-SYNTHETIC",
                "obligation_period": "2026-06",
                "expected_members": 1,
                "expected_rows": 3,
                "control_totals": {"INR": "3600"},
                "label": "SYNTHETIC reported PF contributions",
            },
        )
        dest = ROOT / ".local-runtime/country-workflows/fixture.json"
        from tests.unit.pdf_bank_example import layout as pdf_layout
        from tests.unit.pdf_bank_example import statement as pdf_statement
        from tests.unit.test_credit_applications import population as credit_population
        from tests.unit.test_withholding_workflows import pooled_certificate_population
        from tests.unit.test_withholding_workflows import population as withholding_population

        await grant(client, h, f"/api/v1/engagements/{india}/audit", supporting_reviewer)
        credit_sources = {}
        for country, engagement, currency in (("AE", eid, "AED"), ("IN", india, "INR")):
            credit_sources[country] = {}
            for role, rows in credit_population().items():
                for row in rows:
                    row["currency"] = currency
                kind = {
                    "items": "audit-open-items",
                    "controls": "balance-controls",
                    "applications": "credit-applications",
                }[role]
                total = "25" if role == "applications" else "60"
                prepared = await source(
                    client,
                    h,
                    engagement,
                    rows,
                    f"SYNTHETIC {country} credit {role}",
                    kind,
                    {currency: total},
                )
                approved = await decision(client, supporting_reviewer[0], engagement, prepared)
                assert approved.status_code == 201, approved.text
                credit_sources[country][role] = approved.json()["id"]
        withholding_sources = {}
        for scope in ("deductor", "collectee", "collectee-cap"):
            legal_role = "deductor" if scope == "deductor" else "collectee"
            withholding_sources[scope] = {}
            assessment_bytes = b"%PDF-1.4\nSYNTHETIC ASSESSMENT ONLY " + scope.encode() + b"\n%%EOF"
            assessment_id = await native_file(
                india, f"SYNTHETIC-{scope}-assessment.pdf", assessment_bytes, "application/pdf"
            )
            populations = (
                pooled_certificate_population()
                if scope == "collectee-cap"
                else withholding_population(legal_role)
            )
            for role, rows in populations.items():
                for row in rows:
                    row.update(
                        legal_role=legal_role, tax_kind="TDS" if legal_role == "deductor" else "TCS"
                    )
                    if row.get("assessment_evidence_version_id"):
                        row.update(
                            assessment_evidence_version_id=assessment_id,
                            assessment_sha256=hashlib.sha256(assessment_bytes).hexdigest(),
                        )
                if role in {"reported", "statement"}:
                    rows.append(
                        {
                            **rows[0],
                            "id": "superseded",
                            "source_version": "0",
                            "record_status": "superseded",
                            "amount": "150",
                        }
                    )
                if legal_role == "deductor" and role == "reported":
                    rows[0]["amount"] = "90"
                total = str(sum(Decimal(row["amount"]) for row in rows))
                prepared = await source(
                    client,
                    h,
                    india,
                    rows,
                    f"SYNTHETIC {scope} {role}",
                    "withholding-records",
                    {"INR": total},
                )
                approved = await decision(client, supporting_reviewer[0], india, prepared)
                assert approved.status_code == 201, approved.text
                withholding_sources[scope][role] = approved.json()["id"]
        from tests.unit.test_import_vat import line as import_vat_line

        import_vat_sources = {}
        for role in ("customs", "portal", "books", "customs-ambiguous"):
            import_rows = [
                import_vat_line(),
                import_vat_line(
                    id="ADJ-1",
                    entry_kind="adjustment",
                    adjustment_reference="ADJ-1",
                    net="-100",
                    tax="-5",
                ),
            ]
            if role == "customs-ambiguous":
                import_rows.append(import_vat_line(id="IMPORT-REV2", record_version="2"))
            for import_row in import_rows:
                import_row["evidence_reference"] = f"SYNTHETIC-{role}-{import_row['id']}"
            import_prepared = await source(
                client,
                h,
                eid,
                import_rows,
                f"SYNTHETIC {role} import VAT details",
                table_type="import-vat-lines",
                totals={"AED": "95" if role == "customs-ambiguous" else "45"},
                import_taxable_base_control="1900" if role == "customs-ambiguous" else "900",
            )
            import_reviewed = await decision(client, supporting_reviewer[0], eid, import_prepared)
            assert import_reviewed.status_code == 201, import_reviewed.text
            import_vat_sources[role] = import_reviewed.json()["id"]
        import_box_parent = await execute(
            client,
            h,
            eid,
            "country-workflow",
            {
                "workflow": "uae-import-vat",
                "source_ids": {
                    role: import_vat_sources[role] for role in ("customs", "portal", "books")
                },
                "as_of": "2026-06-30",
                "currency": "AED",
                "title": "SYNTHETIC reviewed import detail for box bridge",
                "rationale": "Independent assessed import details and signed corrections reviewed for selected-box comparison only",
            },
        )
        import_box_approved = await decision(client, supporting_reviewer[0], eid, import_box_parent)
        assert import_box_approved.status_code == 201, import_box_approved.text
        from tests.unit.test_vat_box_scope import full_filed_boxes

        import_filed = await source(
            client,
            h,
            eid,
            full_filed_boxes(),
            "SYNTHETIC independently retained filed import boxes",
            table_type="return-boxes",
            totals={"AED": "230"},
        )
        import_filed_approved = await decision(client, supporting_reviewer[0], eid, import_filed)
        assert import_filed_approved.status_code == 201, import_filed_approved.text
        pdf_evidence, pdf_books = {}, {}
        pdf_final_reviewer = await actor(h, "Firm Administrator", "browser-pdf-final-reviewer")
        for country, engagement, currency in (("AE", eid, "AED"), ("IN", india, "INR")):
            await grant(client, h, f"/api/v1/engagements/{engagement}/audit", pdf_final_reviewer)
            pdf_evidence[country] = await native_file(
                engagement,
                f"SYNTHETIC-{country}-bank-grid.pdf",
                pdf_statement(currency),
                "application/pdf",
            )
            pdf_book = await source(
                client,
                h,
                engagement,
                [
                    transaction(
                        id="PDF-BOOK-1",
                        reference="REF-1",
                        date="2026-06-30",
                        amount="100.25",
                        currency=currency,
                        counterparty="SYN-CLIENT",
                    ),
                    transaction(
                        id="PDF-BOOK-2",
                        reference="REF-2",
                        date="2026-06-30",
                        amount="-5",
                        currency=currency,
                        counterparty="SYN-CLIENT",
                    ),
                ],
                f"SYNTHETIC {country} independent PDF cashbook",
                totals={currency: "95.25"},
            )
            approved = await decision(client, supporting_reviewer[0], engagement, pdf_book)
            assert approved.status_code == 201, approved.text
            pdf_books[country] = approved.json()["id"]
        # Dedicated history engagement: never crowd the other workflow fixtures.
        history_response = await client.post(
            "/api/v1/engagements",
            headers=h,
            json={
                "entity_id": opts["entity_id"],
                "period_id": opts["period_id"],
                "name": "SYNTHETIC source history pagination",
                "engagement_type": "External Audit",
            },
        )
        assert history_response.status_code == 201, history_response.text
        history_eid = history_response.json()["id"]
        await grant(client, h, f"/api/v1/engagements/{history_eid}/audit", supporting_reviewer)
        history_source = await source(
            client, h, history_eid, [transaction()], "SYNTHETIC retained older approved cashbook"
        )
        history_approval = await decision(
            client, supporting_reviewer[0], history_eid, history_source
        )
        assert history_approval.status_code == 201, history_approval.text
        import uuid

        from app.db.session import Session, tenant_context
        from app.modules.intelligence.models import IntelligenceEvent

        async with Session() as history_db, history_db.begin():
            await tenant_context(history_db, h["X-Tenant-ID"])
            for index in range(105):
                placeholder_id = uuid.uuid4()
                history_db.add(
                    IntelligenceEvent(
                        id=placeholder_id,
                        root_id=placeholder_id,
                        version=1,
                        tenant_id=uuid.UUID(h["X-Tenant-ID"]),
                        engagement_id=uuid.UUID(history_eid),
                        kind="source-table",
                        body={
                            "source_filename": f"SYNTHETIC unreviewed history placeholder {index}"
                        },
                        dependencies=[],
                        sha256="0" * 64,
                    )
                )
        if implementation_hash() != implementation:
            raise RuntimeError(
                "Backend implementation changed during fixture preparation; prepare fresh fixtures before browser verification"
            )
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(
            json.dumps(
                {
                    "synthetic": True,
                    "import_vat_sources": import_vat_sources,
                    "import_box_parent": import_box_approved.json()["id"],
                    "import_filed_source": import_filed_approved.json()["id"],
                    "history_engagement": history_eid,
                    "history_source": history_approval.json()["id"],
                    "credit_application_sources": credit_sources,
                    "withholding_sources": withholding_sources,
                    "pdf_bank_evidence": pdf_evidence,
                    "pdf_bank_books": pdf_books,
                    "pdf_bank_layouts": {"AE": pdf_layout("AED"), "IN": pdf_layout("INR")},
                    "pdf_table_reviewer_email": "browser-supporting-table-reviewer@synthetic.example",
                    "pdf_final_reviewer_email": "browser-pdf-final-reviewer@synthetic.example",
                    "implementation_sha256": implementation,
                    "scanner_test_double": True,
                    "broker_test_double": True,
                    "uae_engagement": eid,
                    "uae_result": result["id"],
                    "uae_vat_result": vat_result["id"],
                    "uae_book_source": book["id"],
                    "uae_statement_source": statement["id"],
                    "india_engagement": india,
                    "india_result": gst["id"],
                    "camt_evidence": camt_evidence,
                    "wps_evidence": wps_evidence,
                    "mapped_bank_evidence": mapped_evidence,
                    "xlsx_bank_evidence": xlsx_ids["bank"],
                    "xlsx_open_items_evidence": xlsx_ids["open-items"],
                    "reviewed_xlsx_bank": supporting_ids["bank"],
                    "reviewed_xlsx_open_items": supporting_ids["open-items"],
                    "extended_book_source": extended_books["id"],
                    "payable_controls": payable_controls["id"],
                    "india_invoice_evidence": india_evidence,
                    "india_ecr_evidence": ecr_evidence,
                    "india_gstr2b_evidence": gstr2b_evidence,
                    "india_gstr2b_books": gstr2b_books["id"],
                    "india_payroll_bases": payroll_bases["id"],
                    "india_payroll_rules": reviewed_rules.json()["id"],
                    "india_payroll_reported": payroll_reported["id"],
                    "tenant": h["X-Tenant-ID"],
                },
                indent=2,
            )
        )
        print(
            "Prepared explicitly synthetic UAE/India browser fixtures in the owned disposable database"
        )
    finally:
        patch.undo()
        await fixture.aclose()


asyncio.run(main())
