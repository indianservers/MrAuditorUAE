"""Seed the owned disposable workflow database for browser verification only.

All documents are synthetic. Malware scanning and broker dispatch are explicit
in-process test doubles during fixture preparation, never server configuration.
"""

import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


async def main():
    from app.core.config import settings

    if (
        settings().environment != "test"
        or not settings().database_url.endswith("/auditos_country_workflows_test")
        or os.getenv("INTEGRATION_TESTS") != "1"
    ):
        raise SystemExit(
            "Only the owned disposable country workflow test database is allowed"
        )
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

        camt_evidence = await native_file(
            eid, "SYNTHETIC-native-camt.xml", CAMT, "application/xml"
        )
        wps_evidence = await native_file(eid, SIF_FILENAME, SIF, "text/csv")
        india_evidence = await native_file(
            india,
            "SYNTHETIC-native-inv01.json",
            json.dumps(invoice()).encode(),
            "application/json",
        )
        ecr_evidence = await native_file(
            india, "SYNTHETIC-monthly-ecr.txt", ECR, "text/plain"
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
        rule_reviewer = await actor(
            h, "Firm Administrator", "country-payroll-rule-reviewer"
        )
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
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(
            json.dumps(
                {
                    "synthetic": True,
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
