import io
import os
from pathlib import Path

import pytest
from openpyxl import load_workbook

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries
from tests.qa_crud.test_india_ecr_source import india_context
from tests.qa_crud.test_uae_ct_audit_duty import ORIGINAL as MD84
from tests.qa_crud.test_uae_ct_audit_duty import upload
from tests.unit.test_uae_company_accounts import sample
from tests.unit.test_uae_ct_audit_duty import sample as ct_sample

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable DB required"
)
FOLDER = (
    Path(__file__).resolve().parents[3]
    / "docs/country-workflows/authority-references/uae-company-law-2026-10-31"
)


async def context(c):
    h, _, existing, _ = await setup(c)
    eng = (await c.get(f"/api/v1/engagements/{existing}", headers=h)).json()
    period = await c.post(
        "/api/v1/financial-periods",
        headers=h,
        json={"entity_id": eng["entity_id"], "start_date": "2025-01-01", "end_date": "2025-12-31"},
    )
    assert period.status_code == 201, period.text
    result = await c.post(
        "/api/v1/engagements",
        headers=h,
        json={
            "entity_id": eng["entity_id"],
            "period_id": period.json()["id"],
            "name": "SYNTHETIC completed company fiscal year",
            "engagement_type": "External Audit",
        },
    )
    assert result.status_code == 201, result.text
    eid = result.json()["id"]
    return h, eid, f"/api/v1/engagements/{eid}/audit"


async def documents(c, h, base, *, adoption_headers=None, altered=False):
    files = {}
    for role, name, content, media in [
        (
            "law",
            "original-law.pdf",
            (FOLDER / "moet-hosted-companies-law32-2021-english.pdf").read_bytes()
            + (b"\n" if altered else b""),
            "application/pdf",
        ),
        (
            "amendment",
            "original-amendment.pdf",
            (FOLDER / "fdl20-2025-arabic-original.pdf").read_bytes(),
            "application/pdf",
        ),
        (
            "adoption",
            "SYNTHETIC-operative-adoption.txt",
            b"SYNTHETIC independently adopted whole-period source chain and declared publication 2025-11-01; this is not the actual Gazette date or real legal qualification",
            "text/plain",
        ),
        (
            "facts",
            "SYNTHETIC-company-facts.txt",
            b"SYNTHETIC LLC, CCL applies, completed valid FY2025, no written requests; resident taxable person, not Tax Group or QFZP, exact full-year revenue AED0; no actual client qualification",
            "text/plain",
        ),
    ]:
        files[role] = await upload(
            c,
            adoption_headers if role == "adoption" and adoption_headers else h,
            base,
            name,
            content,
            media,
        )
    payload = sample(
        law_evidence_version_id=files["law"][1]["id"],
        amendment_evidence_version_id=files["amendment"][1]["id"],
        adoption_evidence_version_id=files["adoption"][1]["id"],
        adoption_sha256=files["adoption"][1]["sha256"],
        fact_evidence_version_id=files["facts"][1]["id"],
        fact_sha256=files["facts"][1]["sha256"],
    )
    return files, payload


@pytest.mark.parametrize("changed_role", ["law", "amendment", "adoption", "facts"])
async def test_company_law_review_exports_and_every_document_role_stales_history(
    environment, monkeypatch, changed_role
):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base = await context(c)
    reviewer = await actor(h, "Firm Administrator", "company-accounts-reviewer")
    await grant(c, h, base, reviewer)
    files, data = await documents(c, h, base)
    prefix = f"/api/v1/intelligence/engagements/{eid}"
    response = await c.post(prefix + "/uae-company-accounts-duty", headers=h, json=data)
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["body"]["rows"][0]["annual_audit_required"] is True
    assert result["body"]["rows"][0]["minimum_register_retention_years"] == 5
    assert (await decision(c, h, eid, result)).status_code == 403
    approved = await decision(c, reviewer[0], eid, result)
    assert approved.status_code == 201, approved.text
    reviewed = approved.json()
    path = prefix + "/events/" + reviewed["id"]
    export = await c.get(path + "/export?format=xlsx", headers=h)
    assert export.status_code == 200, export.text
    book = load_workbook(io.BytesIO(export.content), read_only=True)
    rows = list(book["Rows"].values)
    assert str(rows[1][rows[0].index("annual_audit_required")]).lower() == "true"
    assert str(rows[1][rows[0].index("minimum_register_retention_years")]) == "5"
    assert str(rows[1][rows[0].index("entity_audit_exemption_established")]).lower() == "false"
    book.close()
    ct_result = None
    if changed_role == "adoption":
        _, ct_original = await upload(
            c, h, base, "original-md84.pdf", MD84.read_bytes(), "application/pdf"
        )
        ct = ct_sample(
            tax_period_start="2025-01-01",
            tax_period_end="2025-12-31",
            revenue_aed="0",
            rule_evidence_version_id=ct_original["id"],
            fact_evidence_version_id=files["facts"][1]["id"],
            fact_sha256=files["facts"][1]["sha256"],
        )
        ct_response = await c.post(prefix + "/uae-ct-audit-duty", headers=h, json=ct)
        assert ct_response.status_code == 201, ct_response.text
        ct_result = ct_response.json()
        assert ct_result["body"]["rows"][0]["audited_financial_statements_required"] is False
        assert ct_result["body"]["rows"][0]["entity_audit_exemption_established"] is False
    changed = await c.post(
        base + "/evidence-files/" + files[changed_role][0]["id"],
        headers=h,
        files={
            "file": (
                "SYNTHETIC-replaced-source.txt",
                b"SYNTHETIC corrected original requires independent reassessment",
                "text/plain",
            )
        },
    )
    assert changed.status_code == 201, changed.text
    stale = await c.get(path, headers=h)
    assert stale.status_code == 200 and stale.json()["freshness"] == "STALE"
    assert stale.json()["body"] == reviewed["body"]
    assert (await decision(c, reviewer[0], eid, reviewed)).status_code == 409
    assert (
        await c.post(prefix + "/uae-company-accounts-duty", headers=h, json=data)
    ).status_code == 409
    if ct_result:
        ct_path = prefix + "/events/" + ct_result["id"]
        assert (await c.get(ct_path, headers=h)).json()["freshness"] == "CURRENT"
        await c.post(
            base + "/evidence-files/" + files["facts"][0]["id"],
            headers=h,
            files={
                "file": (
                    "SYNTHETIC-revised-company.txt",
                    b"SYNTHETIC changed shared facts invalidate every dependent assessment",
                    "text/plain",
                )
            },
        )
        changed_ct = (await c.get(ct_path, headers=h)).json()
        assert changed_ct["freshness"] == "STALE"
        assert changed_ct["body"] == ct_result["body"]


@pytest.mark.parametrize(
    "failure",
    ["wrong-original", "fact-hash", "other-country", "wrong-period", "integrity", "unavailable"],
)
async def test_country_period_original_and_integrity_guards(environment, monkeypatch, failure):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base = (
        await india_context(c, year=2025) if failure == "other-country" else await context(c)
    )
    _, data = await documents(c, h, base, altered=failure == "wrong-original")
    if failure == "fact-hash":
        data["fact_sha256"] = "c" * 64
    if failure == "wrong-period":
        data["fiscal_year_end"] = "2025-12-30"
    if failure in {"integrity", "unavailable"}:
        from app.modules.country_workflows import service

        def failed_hash(_):
            if failure == "unavailable":
                raise OSError("SYNTHETIC-private-object-path-must-not-leak")
            return "0" * 64

        monkeypatch.setattr(service, "hash_file", failed_hash)
    response = await c.post(
        f"/api/v1/intelligence/engagements/{eid}/uae-company-accounts-duty", headers=h, json=data
    )
    assert response.status_code == 422, response.text
    assert "SYNTHETIC-private-object-path-must-not-leak" not in response.text


async def test_legal_adoption_document_preparer_is_not_an_independent_reviewer(
    environment, monkeypatch
):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base = await context(c)
    legal = await actor(h, "Firm Administrator", "company-legal-preparer")
    reviewer = await actor(h, "Firm Administrator", "company-independent-reviewer")
    for person in [legal, reviewer]:
        await grant(c, h, base, person)
    _, data = await documents(c, h, base, adoption_headers=legal[0])
    result = await c.post(
        f"/api/v1/intelligence/engagements/{eid}/uae-company-accounts-duty", headers=h, json=data
    )
    assert result.status_code == 201, result.text
    assert (await decision(c, legal[0], eid, result.json())).status_code == 403
    approved = await decision(c, reviewer[0], eid, result.json())
    assert approved.status_code == 201, approved.text
