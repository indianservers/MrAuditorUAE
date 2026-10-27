"""Country source/review/report/export path using real DB and retained CSV."""

import hashlib
import io
import os

import pytest
from pypdf import PdfReader
from pypdf.generic import ContentStream

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, grant
from tests.qa_crud.report_requirement_fixtures import declared_requirements
from tests.qa_crud.test_country_workflows import decision, double_boundaries, source
from tests.qa_crud.test_generic_candidates import context
from tests.unit.country_workflow_cases import transaction

pytestmark = pytest.mark.skipif(os.getenv("INTEGRATION_TESTS") != "1", reason="Owned DB")


@pytest.mark.parametrize(
    "country,category,party,currency",
    [
        ("AE", "uae-ifrs", "شركة النور للتجارة", "AED"),
        ("IN", "india-statutory", "भारत आपूर्तिकर्ता", "INR"),
        ("IN", "india-statutory", "தமிழ் வணிகர்", "INR"),
        ("IN", "india-statutory", "తెలుగు వ్యాపారి", "INR"),
    ],
)
async def test_reviewed_country_report_unicode_pdf_and_unsupported_text(
    environment, monkeypatch, country, category, party, currency
):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, audit = await context(c, country)
    reviewer = await actor(h, "Firm Administrator", f"unicode-report-reviewer-{country}")
    await grant(c, h, audit, reviewer)
    result = await source(
        c,
        h,
        eid,
        [transaction(counterparty=party, currency=currency, amount="105.00")],
        "SYNTHETIC multilingual report source",
        totals={currency: "105.00"},
    )
    approved = await decision(c, reviewer[0], eid, result)
    assert approved.status_code == 201, approved.text
    result = approved.json()
    prefix = f"/api/v1/regulatory/engagements/{eid}"
    for title, expected in [(party, 200), ("Unsupported 中", 422)]:
        template = await c.post(
            prefix + "/report-templates",
            headers=h,
            json={
                "title": title,
                "category": category,
                **declared_requirements("source"),
                "rationale": "Synthetic independently reviewed source-bound draft",
                "blocks": [
                    {
                        "key": "source",
                        "requirement_keys": ["source"],
                        "title": party,
                        "kind": "financial_table",
                        "source_kind": "intelligence",
                        "source_id": result["id"],
                        "text": "Synthetic report; no legal form qualification",
                    }
                ],
            },
        )
        assert template.status_code == 201, template.text
        reviewed = await decision(c, reviewer[0], eid, template.json())
        assert reviewed.status_code == 201, reviewed.text
        report = await c.post(
            prefix + "/reports",
            headers=h,
            json={
                "template_id": reviewed.json()["id"],
                "rationale": "Synthetic independently reviewed source and template",
            },
        )
        assert report.status_code == 201, report.text
        export = f"/api/v1/intelligence/engagements/{eid}/events/{report.json()['id']}/export"
        pdf = await c.get(export + "?format=pdf", headers=h)
        assert pdf.status_code == expected, pdf.text[:200] if expected != 200 else ""
        if expected == 422:
            assert "content-disposition" not in pdf.headers
            assert "U+4E2D" in pdf.json()["error"]["message"]
            assert (await c.get(export + "?format=xlsx", headers=h)).status_code == 200
            continue
        assert pdf.headers["x-export-sha256"] == hashlib.sha256(pdf.content).hexdigest()
        reader = PdfReader(io.BytesIO(pdf.content))
        logical = "\n".join(
            str(args[1]["/ActualText"])
            for page in reader.pages
            for args, operator in ContentStream(page.get_contents(), reader).operations
            if operator == b"BDC"
        )
        assert party in logical and "105.00" in logical
        assert result["id"] in logical and "CURRENT" in logical
        assert "DRAFT" in logical and "NOT SIGNED OR FILED" in logical
