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
    from app.core.operations_contracts import (
        country_workflow_hash as implementation_hash,
    )

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
    from tests.unit.native_source_examples import SIF, SIF_FILENAME
    from tests.unit.test_camt_pages import packet as camt_packet
    from tests.unit.test_india_ecr_source import ECR
    from tests.unit.test_india_gstr2b_source import payload as gstr2b_payload
    from tests.unit.test_india_invoice_source import invoice
    from tests.unit.test_mt940_pages import packet
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

        camt_evidence = await native_file(eid, "SYNTHETIC-native-camt.xml", camt_packet(), "application/xml")
        mt940_evidence = await native_file(
            eid, "SYNTHETIC-paged-AE.mt940", packet("AED", middle=True, fin=True), "text/plain"
        )
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
        india_mt940_evidence = await native_file(
            india, "SYNTHETIC-paged-IN.mt940", packet("INR", middle=True, fin=True), "text/plain"
        )
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
        from tests.unit.test_withholding_workflows import (
            population as withholding_population,
        )

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
        from tests.unit.test_bank_clearance import population as clearance_population

        clearance_fixtures = {}
        for country, engagement, currency in (("AE", eid, "AED"), ("IN", india, "INR")):
            common = transaction(id="MATCH", reference="SYN-MATCH", amount="50", currency=currency, date="2026-06-10", counterparty="")
            original_books = await source(client, h, engagement, [common, {
                **common, "id": "O1", "reference": "SYN-CHEQUE", "date": "2026-06-20", "amount": "-100",
            }], f"SYNTHETIC {country} clearance original cashbook", totals={currency: "-50"})
            original_bank = await source(client, h, engagement, [{**common, "id": "BANK-MATCH"}],
                f"SYNTHETIC {country} clearance original bank", totals={currency: "50"})
            reviewed = []
            for original in (original_books, original_bank):
                approval = await decision(client, supporting_reviewer[0], engagement, original)
                assert approval.status_code == 201, approval.text
                reviewed.append(approval.json())
            brs = await execute(client, h, engagement, "country-workflow", bank_payload(
                *reviewed, currency=currency, book_closing="-50", statement_closing="50"))
            disposition = await decision(client, h, engagement, brs, action="accept", item_id="books:O1")
            assert disposition.status_code == 201, disposition.text
            approved = await decision(client, supporting_reviewer[0], engagement, disposition.json())
            assert approved.status_code == 201, approved.text
            clearance_fixtures[country] = {"brs": approved.json()["id"]}
            later = clearance_population(currency)
            later["allocations"][0].update(outstanding_id="books:O1", amount="100")
            for role, kind in (("statement", "transactions"), ("allocations", "bank-clearances")):
                imported = await source(client, h, engagement, later[role], f"SYNTHETIC {country} later {role}",
                    table_type=kind, totals={currency: "100" if role == "allocations" else "-100"})
                approval = await decision(client, supporting_reviewer[0], engagement, imported)
                assert approval.status_code == 201, approval.text
                clearance_fixtures[country][role] = approval.json()["id"]

        from tests.unit.test_dues_allocations import example as dues_example

        dues_fixtures = {}
        for country, engagement, currency in (("AE", eid, "AED"), ("IN", india, "INR")):
            dues_fixtures[country] = {}
            population = dues_example(currency, "SALARY" if country == "AE" else "PF:EMPLOYEE")
            for role, kind in (("expected", "obligations"), ("reported", "obligations"), ("bank", "transactions"), ("allocations", "obligation-allocations")):
                imported = await source(client, h, engagement, population[role], f"SYNTHETIC {country} bank-linked dues {role}",
                    table_type=kind, totals={currency: "-180" if role == "bank" else "180"})
                approval = await decision(client, supporting_reviewer[0], engagement, imported)
                assert approval.status_code == 201, approval.text
                dues_fixtures[country][role] = approval.json()["id"]

        from country_regulatory_fixture import prepare as prepare_regulatory

        regulatory_conversions = await prepare_regulatory(client, h, opts["client_id"], pdf_final_reviewer)
        from country_pension_fixture import prepare as prepare_pension
        from country_pension_fixture import (
            prepare_published as prepare_published_pension,
        )

        pension_sources = await prepare_pension(client, h, eid, supporting_reviewer)
        published_pension = await prepare_published_pension(
            client, h, regulatory_conversions["AE"]["engagement"], pdf_final_reviewer
        )
        from contribution_fixture import prepare as prepare_contributions

        contribution_settlements = await prepare_contributions(
            client, h, regulatory_conversions, published_pension, pdf_final_reviewer
        )
        from tests.qa_crud.test_gstr2b_parts import retained_bundle

        gstr2b_bundle_input, _ = await retained_bundle(
            client, h, india, f"/api/v1/engagements/{india}/audit"
        )
        bundle_books = await source(
            client,
            h,
            india,
            [
                document(
                    id=f"B{index}",
                    registration="27ABCDE5678G1Z8",
                    counterparty="29ABCDE1234F1Z5",
                    reference=f"SYNTHETIC-{index}",
                    date="2026-06-15",
                    currency="INR",
                    component="IGST",
                    net=net,
                    tax=tax,
                )
                for index, net, tax in ((1, "100", "18"), (2, "50", "9"))
            ],
            "SYNTHETIC independent numbered-return purchase register",
            "tax-documents",
            {"INR": "27"},
        )
        bundle_books_approval = await decision(
            client, supporting_reviewer[0], india, bundle_books
        )
        assert bundle_books_approval.status_code == 201, bundle_books_approval.text
        composed_import = await client.post(
            f"/api/v1/intelligence/engagements/{eid}/events/{import_box_approved.json()['id']}/import-vat-box-source",
            headers=h,
            json={"source_role": "books", "label": "SYNTHETIC import component for composed VAT201",
                  "assessment": "Independent selected book declarations and signed import corrections for composition",
                  "boxes": {"6": {"expected_rows": 1, "taxable_amount": "1000", "tax": "50"},
                            "7": {"expected_rows": 1, "taxable_amount": "-100", "tax": "-5"}}},
        )
        assert composed_import.status_code == 201, composed_import.text
        composed_import_approval = await decision(client, pdf_final_reviewer[0], eid, composed_import.json())
        assert composed_import_approval.status_code == 201, composed_import_approval.text
        composed_other = await source(
            client, h, eid, [row for row in full_filed_boxes() if row["box"] not in {"6", "7"}],
            "SYNTHETIC other twelve explicit VAT201 book boxes", "return-boxes", {"AED": "185"},
        )
        composed_other_approval = await decision(client, pdf_final_reviewer[0], eid, composed_other)
        assert composed_other_approval.status_code == 201, composed_other_approval.text
        from tests.unit.test_wps_variable_pay import SIF_EVP
        from tests.unit.test_wps_variable_pay import options as evp_options

        evp_evidence = await native_file(eid, SIF_FILENAME, SIF_EVP, "text/csv")
        evp_input = evp_options(evidence_version_id=evp_evidence).model_dump(mode="json")
        from tests.qa_crud.test_inventory_controlled_bridge import (
            retain as retain_inventory,
        )

        inventory_controls = {}
        for country, engagement, currency in (("AE", eid, "AED"), ("IN", india, "INR")):
            originals, _, quantity_controls = await retain_inventory(client, h, engagement, currency)
            reviewed_ids = {}
            for role in ("books", "counts"):
                approved = await decision(client, supporting_reviewer[0], engagement, originals[role])
                assert approved.status_code == 201, approved.text
                reviewed_ids[role] = approved.json()["id"]
            inventory_controls[country] = {"engagement": engagement, "currency": currency,
                "source_ids": reviewed_ids,
                "movement_evidence": originals["movements"]["body"]["evidence_version_id"],
                "movement_controls": quantity_controls["movements"]}
        from country_gst_summary_fixture import prepare as prepare_gst_summary
        from country_gstr1_documents_fixture import prepare as prepare_gstr1_documents
        from country_invoice_register_fixture import prepare as prepare_invoice_register

        invoice_register = await prepare_invoice_register(client, h, india, supporting_reviewer, native_file)
        gst_summary = await prepare_gst_summary(client, h, india, supporting_reviewer, native_file)
        gstr1_documents = await prepare_gstr1_documents(client, h, india, supporting_reviewer)

        from tests.qa_crud.test_vat_emirates import (
            prepare_sources as prepare_emirate_sources,
        )

        emirate_components, emirate_filed = await prepare_emirate_sources(client, h, eid, supporting_reviewer)

        from country_payroll_ledger_fixture import prepare as prepare_payroll_ledger

        payroll_ledger = await prepare_payroll_ledger(client, h, (("AE", eid, "AED"), ("IN", india, "INR")), supporting_reviewer)

        from country_bank_carryforward_fixture import prepare as prepare_carryforward

        bank_carryforward = await prepare_carryforward(client, h, (("AE", eid, "AED"), ("IN", india, "INR")), supporting_reviewer)

        from tests.qa_crud.test_ecr_arrears import obligations as arrear_obligations
        from tests.qa_crud.test_ecr_arrears import retain as retain_arrears

        arrear_input, _ = await retain_arrears(client, h, india, f"/api/v1/engagements/{india}/audit")
        arrear_source_ids = {}
        for role in ("expected", "payment"):
            prepared = await source(client, h, india, arrear_obligations(role),
                "SYNTHETIC independently assessed arrear " + role, "obligations", {"INR": "360"})
            approved = await decision(client, supporting_reviewer[0], india, prepared)
            assert approved.status_code == 201, approved.text
            arrear_source_ids[role] = approved.json()["id"]
        bank_dates = {}
        for code, engagement, currency in [("AE", eid, "AED"), ("IN", india, "INR")]:
            date_rows = [{"id": f"B-{index}", "account": "BANK-1", "reference": f"SYN-DATE-{index}", "date": "2026-06-01", "currency": currency, "amount": "1", "bank_booking_date": "2026-06-01", "bank_value_date": "2026-06-30", "bank_date_basis": "BOOKING_DATE"} for index in range(101)]
            date_results = {}
            date_book = await source(client, h, engagement, date_rows, "SYNTHETIC independently assessed booking-date books", totals={currency: "101"})
            book_approval = await decision(client, pdf_final_reviewer[0], engagement, date_book)
            assert book_approval.status_code == 201, book_approval.text
            for mode in ("fallback", "explicit"):
                statement_rows = [{**row, "id": "S-" + row["id"], **({"bank_booking_date": "", "bank_value_date": "2026-06-01", "bank_date_basis": "VALUE_DATE_FALLBACK"} if mode == "fallback" else {})} for row in date_rows]
                date_statement = await source(client, h, engagement, statement_rows, "SYNTHETIC " + mode + " statement date evidence", totals={currency: "101"})
                statement_approval = await decision(client, pdf_final_reviewer[0], engagement, date_statement)
                assert statement_approval.status_code == 201, statement_approval.text
                date_result = await execute(client, h, engagement, "country-workflow", bank_payload(book_approval.json(), statement_approval.json(), currency=currency, book_closing="101", statement_closing="101", title="SYNTHETIC " + code + " " + mode + " bank dates"))
                date_results[mode] = date_result["id"]
            bank_dates[code] = {"engagement": engagement, **date_results}
        from tests.unit.test_bank_accounts import parameters as account_parameters
        from tests.unit.test_bank_accounts import population as account_population

        bank_account_evidence = {}
        for code, engagement in [("AE", eid), ("IN", india)]:
            engagement_record = (await client.get("/api/v1/engagements/" + engagement, headers=h)).json()
            entity_record = (await client.get("/api/v1/entities/" + engagement_record["entity_id"], headers=h)).json()
            account_rows = account_population(code)
            account_sources = {}
            for role, observations in account_rows.items():
                observations[0]["owner_name"] = entity_record["name"]
                prepared = await source(client, h, engagement, observations, "SYNTHETIC account evidence " + role, "bank-account-evidence", {})
                approval = await decision(client, pdf_final_reviewer[0], engagement, prepared)
                assert approval.status_code == 201, approval.text
                account_sources[role] = approval.json()["id"]
            wrong_rows = [{**account_rows["bank"][0], "id":"SYNTHETIC-wrong-owner", "owner_identifier":"UNRELATED-OWNER"}]
            prepared = await source(client, h, engagement, wrong_rows, "SYNTHETIC mismatched bank owner evidence", "bank-account-evidence", {})
            approval = await decision(client, pdf_final_reviewer[0], engagement, prepared)
            assert approval.status_code == 201, approval.text
            account_parameters_data = account_parameters(code, bank_owner_name=entity_record["name"]).model_dump(mode="json")
            bank_account_evidence[code] = {"engagement": engagement, "sources": account_sources, "mismatched_bank": approval.json()["id"], "parameters": account_parameters_data}
        from tests.qa_crud.test_bank_binding import (
            retain_native as retain_linked_native,
        )
        from tests.unit.native_source_examples import CAMT as linked_camt

        bank_account_binding = {}
        for code in ("AE", "IN"):
            entry = bank_account_evidence[code]
            engagement = entry["engagement"]
            scope = {**entry["parameters"], "source_ids":entry["sources"]}
            prepared = await execute(client,h,engagement,"country-workflow",scope)
            review = await decision(client,pdf_final_reviewer[0],engagement,prepared)
            assert review.status_code == 201, review.text
            currency = scope["currency"]
            number = account_population(code)["bank"][0]["account_number"]
            native,_ = await retain_linked_native(client,h,engagement,linked_camt.replace(b"BANK-1",number.encode()).replace(b"AED",currency.encode()),currency)
            books = await source(client,h,engagement,[{"id":"LINKED-B1","account":scope["account"],"reference":"PAY-1","date":"2026-06-01","currency":currency,"amount":"100"},{"id":"LINKED-B2","account":scope["account"],"reference":"FEE","date":"2026-06-02","currency":currency,"amount":"-5"}],"SYNTHETIC bank alias ledger books",totals={currency:"95"})
            linked_sources = {}
            for role,item in [("books",books),("statement",native)]:
                approved = await decision(client,pdf_final_reviewer[0],engagement,item)
                assert approved.status_code == 201, approved.text
                linked_sources[role] = approved.json()["id"]
            bank_account_binding[code] = {"engagement":engagement,"account":scope["account"],"currency":currency,"original_account":number,"review":review.json()["id"],"sources":linked_sources,"account_bank_source":entry["sources"]["bank"]}
        if implementation_hash() != implementation:
            raise RuntimeError(
                "Backend implementation changed during fixture preparation; prepare fresh fixtures before browser verification"
            )
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(
            json.dumps(
                {
                    "synthetic": True,
                    "bank_dates": bank_dates,
                    "bank_account_evidence": bank_account_evidence,
                    "bank_account_binding": bank_account_binding,
                    "regulatory_conversions": regulatory_conversions,
                    "pension_sources": pension_sources,
                    "published_pension": published_pension,
                    "contribution_settlements": contribution_settlements,
                    "bank_clearance": clearance_fixtures,
                    "obligation_allocations": dues_fixtures,
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
                    "mt940_evidence": mt940_evidence,
                    "india_mt940_evidence": india_mt940_evidence,
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
                    "invoice_register": invoice_register,
                    "gst_summary": gst_summary,
                    "gstr1_documents": gstr1_documents,
                    "emirate_vat": {"components": emirate_components, "filed": emirate_filed},
                    "payroll_ledger": payroll_ledger,
                    "bank_carryforward": bank_carryforward,
                    "ecr_arrear_input": arrear_input,
                    "ecr_arrear_sources": arrear_source_ids,
                    "inventory_controls": inventory_controls,
                    "wps_evp_input": evp_input,
                    "vat_composition_sources": [composed_import_approval.json()["id"], composed_other_approval.json()["id"]],
                    "gstr2b_bundle_input": gstr2b_bundle_input,
                    "gstr2b_bundle_books": bundle_books_approval.json()["id"],
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
