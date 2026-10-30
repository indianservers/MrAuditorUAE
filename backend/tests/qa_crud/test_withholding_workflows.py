import io
import json
import os
from decimal import Decimal

import pytest
from openpyxl import load_workbook

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_annual_tax_statement import PAN, header, portal_header
from tests.unit.test_withholding_workflows import pooled_certificate_population, population

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable DB required"
)


@pytest.mark.parametrize(
    "legal_role",
    [
        "deductor",
        "collectee",
        "collectee-cap",
        "collectee-26AS",
        "collectee-168",
        "collectee-TRACES",
    ],
)
async def test_separate_withholding_sources_review_export_workpaper_and_supersession(
    environment, monkeypatch, legal_role
):
    c = environment
    scope = legal_role
    legal_role = "deductor" if scope == "deductor" else "collectee"
    double_boundaries(monkeypatch)
    h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "withholding-source-reviewer")
    final_reviewer = await actor(h, "Firm Administrator", "withholding-result-reviewer")
    uploader = await actor(h, "Firm Administrator", "withholding-assessment-uploader")
    for person in (reviewer, final_reviewer, uploader):
        await grant(c, h, base, person)
    records = (
        pooled_certificate_population() if scope == "collectee-cap" else population(legal_role)
    )
    for rows in records.values():
        for row in rows:
            row.update(legal_role=legal_role, tax_kind="TDS" if legal_role == "deductor" else "TCS")
            if scope in {"collectee-26AS", "collectee-168", "collectee-TRACES"}:
                row["registration"] = PAN
                if scope == "collectee-26AS":
                    for field in (
                        "tax_year_start",
                        "tax_year_end",
                        "transaction_date",
                        "period",
                        "due_date",
                        "payment_date",
                        "assessment_period_start",
                        "assessment_period_end",
                    ):
                        if row.get(field):
                            row[field] = row[field].replace("2026", "2025").replace("2027", "2026")
    if scope in {"collectee-26AS", "collectee-168", "collectee-TRACES"}:
        year = 2025 if scope == "collectee-26AS" else 2026
        expected_header = portal_header() if scope == "collectee-TRACES" else header(year)
        records["statement"][0]["annual_statement"] = json.dumps(expected_header)
    document_record = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    assessment_bytes = b"%PDF-1.4\nSYNTHETIC WITHHOLDING ASSESSMENT ONLY\n%%EOF"
    assessment_upload = await c.post(
        base + "/evidence-files/" + document_record["id"],
        headers=uploader[0],
        files={"file": ("SYNTHETIC-assessment.pdf", assessment_bytes, "application/pdf")},
    )
    assert assessment_upload.status_code == 201, assessment_upload.text
    assessed_role = "expected" if legal_role == "deductor" else "certificate"
    for row in records[assessed_role]:
        row.update(
            assessment_evidence_version_id=assessment_upload.json()["id"],
            assessment_sha256=assessment_upload.json()["sha256"],
        )
    if legal_role == "deductor":
        invalid = [{**records[assessed_role][0], "assessment_sha256": "0" * 64}]
        await source(
            c,
            h,
            eid,
            invalid,
            "Synthetic mismatched assessment hash",
            "withholding-records",
            {"INR": "100"},
            failed="hash differs",
        )
    for row in records[assessed_role]:
        row.pop("assessment_evidence_version_id")
        row.pop("assessment_sha256")
    statement_role = "reported" if legal_role == "deductor" else "statement"
    records[statement_role].append(
        {
            **records[statement_role][0],
            "id": "superseded",
            "source_version": "0",
            "record_status": "superseded",
            "amount": "150",
        }
    )
    prepared = {}
    for role, rows in records.items():
        total = str(sum((Decimal(row["amount"]) for row in rows), Decimal(0)))
        created = await source(
            c,
            h,
            eid,
            rows,
            "Synthetic withholding " + role,
            "withholding-records",
            {"INR": total},
            **(
                {"rule_document_version_id": assessment_upload.json()["id"]}
                if role == assessed_role
                else {}
            ),
        )
        if role == assessed_role:
            assert (await decision(c, uploader[0], eid, created)).status_code == 403
        reviewed = await decision(c, reviewer[0], eid, created)
        assert reviewed.status_code == 201, reviewed.text
        prepared[role] = reviewed.json()
    payload = {
        "workflow": "india-withholding-liability"
        if legal_role == "deductor"
        else "india-withholding-credit",
        "withholding_role": legal_role,
        "source_ids": {role: obj["id"] for role, obj in prepared.items()},
        "as_of": "2026-06-30",
        "title": "Synthetic separate withholding evidence",
        "rationale": "Explicit assessed legal role and independently selected current observations",
    }
    result = await execute(c, h, eid, "country-workflow", payload)
    row = result["body"]["rows"][0]
    assert row["amounts"][statement_role] == "100"
    assert row["excluded_source_ids"][statement_role] == ["superseded"]
    if scope in {"collectee-26AS", "collectee-168", "collectee-TRACES"}:
        assert row["annual_statement"] == expected_header
        assert result["body"]["annual_statement_scope_contract"] == "india-annual-statement-scope/1"
    if scope == "collectee-cap":
        assert result["body"]["blocked"] and row["comparison_state"] == "MATCHED"
        assert row["state"] == "ASSESSMENT_NOT_SUPPORTED"
        assert row["assessment_provenance"]["certificate_scope_used_amount"] == "200"
        assert (await decision(c, final_reviewer[0], eid, result)).status_code == 409
        disposition = await decision(c, h, eid, result, "accept", item_id=row["id"])
        assert disposition.status_code == 201, disposition.text
        assert (await decision(c, final_reviewer[0], eid, disposition.json())).status_code == 409
        return
    assert row["state"] == "MATCHED" and row["credit_entitlement"] == "NOT_DETERMINED"
    assert (await decision(c, h, eid, result)).status_code == 403
    approved = await decision(c, final_reviewer[0], eid, result)
    assert approved.status_code == 201, approved.text
    identifier = approved.json()["id"]
    prefix = f"/api/v1/intelligence/engagements/{eid}/events"
    exported = await c.get(f"{prefix}/{identifier}/export?format=xlsx", headers=h)
    assert exported.status_code == 200 and exported.content.startswith(b"PK")
    workbook = load_workbook(io.BytesIO(exported.content))
    cover = dict(workbook["Source and review"].values)
    assert cover["withholding_role"] == legal_role
    assert cover["assessment_contract_version"] == "withholding-assessment/1"
    assert cover["comparison_basis"] == (
        "LIABILITY" if legal_role == "deductor" else "BENEFICIARY_CREDIT"
    )
    headers = [cell.value for cell in workbook["Rows"][1]]
    values = [cell.value for cell in workbook["Rows"][2]]
    exported_row = dict(zip(headers, values, strict=True))
    assert "superseded" in exported_row["excluded_source_ids"]
    assert exported_row["credit_entitlement"] == "NOT_DETERMINED"
    assert assessment_upload.json()["id"] in exported_row["assessment_provenance"]
    if scope in {"collectee-26AS", "collectee-168", "collectee-TRACES"}:
        assert json.loads(exported_row["annual_statement"]) == expected_header
        assert json.loads(cover["annual_statement_scopes"]) == [
            {"source_version": "0", **expected_header},
            {"source_version": "1", **expected_header},
        ]
        assert cover["annual_statement_scope_basis"] == (
            "DECLARED_NORMALIZATION_NOT_NATIVE_HEADER_VERIFICATION"
        )
    paper = await c.post(
        f"{prefix}/{identifier}/working-paper",
        headers=h,
        json={
            "reference": "SYN-WITHHOLDING",
            "title": "Synthetic scoped withholding evidence",
            "objective": "Compare role-specific source evidence without asserting legal entitlement",
        },
    )
    assert paper.status_code == 201, paper.text
    # Opposite legal roles are not interchangeable even with identical INR amounts.
    incompatible = "deductee" if legal_role == "deductor" else "collector"
    opposite_workflow = (
        "india-withholding-credit" if incompatible == "deductee" else "india-withholding-liability"
    )
    await execute(
        c,
        h,
        eid,
        "country-workflow",
        {
            **payload,
            "workflow": opposite_workflow,
            "withholding_role": incompatible,
            "source_ids": {role: obj["id"] for role, obj in prepared.items()},
        },
        failed="required source role",
    )
    changed = await c.post(
        base + "/evidence-files/" + document_record["id"],
        headers=h,
        files={
            "file": ("SYNTHETIC-assessment-v2.pdf", assessment_bytes + b"\nnew", "application/pdf")
        },
    )
    assert changed.status_code == 201, changed.text
    source_detail = await c.get(f"{prefix}/{prepared[assessed_role]['id']}", headers=h)
    assert source_detail.status_code == 200 and source_detail.json()["freshness"] == "STALE"
    detail = await c.get(f"{prefix}/{identifier}", headers=h)
    assert detail.status_code == 200 and detail.json()["freshness"] == "STALE"
