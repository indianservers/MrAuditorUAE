import io
import os
from pathlib import Path

import pytest
from openpyxl import load_workbook

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_uae_ct_audit_duty import sample

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable DB required"
)
ORIGINAL = (
    Path(__file__).resolve().parents[3]
    / "docs/country-workflows/authority-references/uae-ct-audit-2025/md84-2025-original.pdf"
)

CLARIFICATION = (
    Path(__file__).resolve().parents[3]
    / "docs/country-workflows/authority-references/uae-tax-group-afs-2026-10-31/ctp007-tax-group-financial-statements-bilingual.pdf"
)


async def upload(c, h, base, name, content, media):
    record = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    response = await c.post(
        base + "/evidence-files/" + record["id"], headers=h, files={"file": (name, content, media)}
    )
    assert response.status_code == 201, response.text
    return record, response.json()


@pytest.mark.parametrize("changed_role", ["facts", "rule", "clarification"])
@pytest.mark.parametrize("group,member", [(False, False), (True, False), (False, True)])
async def test_dated_duty_review_export_and_original_fact_replacement(
    environment, monkeypatch, group, member, changed_role
):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    reviewer = await actor(h, "Firm Administrator", "ct-audit-duty-reviewer")
    await grant(c, h, base, reviewer)
    rule_record, rule = await upload(
        c, h, base, "original-md84.pdf", ORIGINAL.read_bytes(), "application/pdf"
    )
    clarification_record, clarification = await upload(
        c, h, base, "original-ctp007.pdf", CLARIFICATION.read_bytes(), "application/pdf"
    )
    record, facts = await upload(
        c,
        h,
        base,
        "SYNTHETIC-assessed-ct-period-facts.txt",
        b"SYNTHETIC independently assessed tax period, group/QFZP/residency and whole-period revenue",
        "text/plain",
    )
    data = sample(
        rule_evidence_version_id=rule["id"],
        clarification_evidence_version_id=clarification["id"],
        fact_evidence_version_id=facts["id"],
        fact_sha256=facts["sha256"],
        tax_group="assessed_yes" if group else "assessed_no",
        tax_group_member="assessed_yes" if member else "assessed_no",
        revenue_aed=None if group else "50000000.01" if member else "50000000",
    )
    prefix = f"/api/v1/intelligence/engagements/{eid}"
    response = await c.post(prefix + "/uae-ct-audit-duty", headers=h, json=data)
    assert response.status_code == 201, response.text
    result = response.json()
    row = result["body"]["rows"][0]
    assert row["audited_financial_statements_required"] is group
    assert row["tax_group_member"] is member
    assert row["entity_audit_exemption_established"] is False
    assert (await decision(c, h, eid, result)).status_code == 403
    response = await decision(c, reviewer[0], eid, result)
    assert response.status_code == 201, response.text
    reviewed = response.json()
    path = prefix + "/events/" + reviewed["id"]
    exported = await c.get(path + "/export?format=xlsx", headers=h)
    assert exported.status_code == 200, exported.text
    workbook = load_workbook(io.BytesIO(exported.content), read_only=True)
    schedule = list(workbook["Rows"].values)
    exemption = schedule[1][schedule[0].index("entity_audit_exemption_established")]
    assert exemption is False or isinstance(exemption, str) and exemption in {"False", "false"}
    assert "audited_financial_statements_required" in schedule[0]
    workbook.close()
    changed_record = {"facts": record, "rule": rule_record, "clarification": clarification_record}[
        changed_role
    ]
    changed = await c.post(
        base + "/evidence-files/" + changed_record["id"],
        headers=h,
        files={
            "file": (
                "SYNTHETIC-revised-classification.txt",
                b"SYNTHETIC updated tax classifications require independent reassessment",
                "text/plain",
            )
        },
    )
    assert changed.status_code == 201, changed.text
    stale = await c.get(path, headers=h)
    assert stale.status_code == 200 and stale.json()["freshness"] == "STALE"
    assert stale.json()["body"] == reviewed["body"]


@pytest.mark.parametrize(
    "failure",
    [
        "wrong-original",
        "wrong-clarification",
        "quarantined-facts",
        "cloned-rule-facts",
        "other-country",
    ],
)
async def test_source_and_country_boundaries_fail_closed(environment, monkeypatch, failure):
    c = environment
    double_boundaries(monkeypatch)
    if failure == "other-country":
        h, eid, base = await india_context(c)
    else:
        h, _, eid, base = await setup(c)
    raw = ORIGINAL.read_bytes() + (b"\n" if failure == "wrong-original" else b"")
    _, rule = await upload(
        c,
        h,
        base,
        "SYNTHETIC-altered-rule.pdf" if failure == "wrong-original" else "original-rule.pdf",
        raw,
        "application/pdf",
    )
    _, clarification = await upload(
        c,
        h,
        base,
        "original-ctp007.pdf",
        CLARIFICATION.read_bytes() + (b"\n" if failure == "wrong-clarification" else b""),
        "application/pdf",
    )
    if failure == "quarantined-facts":
        double_boundaries(monkeypatch, scan="QUARANTINED")
    _, facts = await upload(
        c,
        h,
        base,
        "SYNTHETIC-ct-facts.txt",
        b"SYNTHETIC independently retained entity facts",
        "text/plain",
    )
    data = sample(
        rule_evidence_version_id=rule["id"],
        clarification_evidence_version_id=clarification["id"],
        fact_evidence_version_id=rule["id"] if failure == "cloned-rule-facts" else facts["id"],
        fact_sha256=rule["sha256"] if failure == "cloned-rule-facts" else facts["sha256"],
    )
    response = await c.post(
        f"/api/v1/intelligence/engagements/{eid}/uae-ct-audit-duty", headers=h, json=data
    )
    assert response.status_code in {409, 422}, response.text
    expected = {
        "wrong-original": "exact original",
        "wrong-clarification": "exact original adopted ctp007",
        "quarantined-facts": "quarantined",
        "cloned-rule-facts": "validation failed",
        "other-country": "uae engagement",
    }[failure]
    assert expected in response.text.lower()


async def test_clarification_preparer_is_also_barred_from_self_approval(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    preparer = await actor(h, "Firm Administrator", "ctp007-original-preparer")
    reviewer = await actor(h, "Firm Administrator", "ctp007-independent-reviewer")
    await grant(c, h, base, preparer)
    await grant(c, h, base, reviewer)
    _, rule = await upload(c, h, base, "md84.pdf", ORIGINAL.read_bytes(), "application/pdf")
    _, clarification = await upload(
        c, preparer[0], base, "ctp007.pdf", CLARIFICATION.read_bytes(), "application/pdf"
    )
    _, facts = await upload(
        c,
        h,
        base,
        "SYNTHETIC-member.txt",
        b"SYNTHETIC independently assessed approved whole-period resident membership and no QFZP",
        "text/plain",
    )
    data = sample(
        tax_group_member="assessed_yes",
        revenue_aed="90000000",
        rule_evidence_version_id=rule["id"],
        clarification_evidence_version_id=clarification["id"],
        fact_evidence_version_id=facts["id"],
        fact_sha256=facts["sha256"],
    )
    response = await c.post(
        f"/api/v1/intelligence/engagements/{eid}/uae-ct-audit-duty", headers=h, json=data
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["body"]["rows"][0]["audited_financial_statements_required"] is False
    assert (await decision(c, preparer[0], eid, result)).status_code == 403
    approved = await decision(c, reviewer[0], eid, result)
    assert approved.status_code == 201, approved.text
