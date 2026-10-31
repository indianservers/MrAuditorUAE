import io
import os

import pytest
from openpyxl import load_workbook

from app.modules.regulatory.caro_index import manifest
from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import action, actor, approve, create, grant
from tests.qa_crud.test_country_workflows import decision, double_boundaries
from tests.qa_crud.test_india_company_scope import documents
from tests.qa_crud.test_india_ecr_source import india_context
from tests.qa_crud.test_uae_ct_audit_duty import upload

pytestmark = pytest.mark.skipif(os.getenv("INTEGRATION_TESTS") != "1", reason="Owned DB required")


async def test_all_caro_matters_bound_to_reviewed_clause_sections_and_stale_evidence(
    environment, monkeypatch
):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base = await india_context(c, year=2025)
    reviewer = await actor(h, "Firm Administrator", "caro-reviewer")
    manager = await actor(h, "Audit Manager", "caro-manager")
    partner = await actor(h, "Audit Partner", "caro-partner")
    for person in (reviewer, manager, partner):
        await grant(c, h, base, person)
    _, data = await documents(c, h, base)
    data["facts"].update(
        small_paid_up_capital="100000001", preceding_financial_year_turnover="1000000001"
    )
    prefix = f"/api/v1/intelligence/engagements/{eid}"
    scoped = await c.post(prefix + "/india-company-reporting-scope", headers=h, json=data)
    assert scoped.status_code == 201, scoped.text
    checked = await decision(c, reviewer[0], eid, scoped.json())
    assert checked.status_code == 201, checked.text
    assert checked.json()["body"]["rows"][0]["caro_full_standalone_matters"] is True
    pack = manifest("india-caro-index:standalone/1")
    evidence, _ = await upload(
        c,
        h,
        base,
        "SYNTHETIC-clause-tests.txt",
        (
            "SYNTHETIC mechanics only, no real legal qualification\n"
            + "\n".join(
                r["key"] + ": synthetic procedure and assessed finding"
                for r in pack["requirements"]
            )
        ).encode(),
        "text/plain",
    )
    evidence = (await c.get(base + "/records/" + evidence["id"], headers=h)).json()
    evidence = await approve(c, h, reviewer[0], base, evidence)
    blocks = []
    for start in (0, 25):
        items = pack["requirements"][start : start + 25]
        paper = await create(
            c,
            h,
            base,
            "working-papers",
            {
                "folder": "SYNTHETIC CARO procedures",
                "sections": [
                    {
                        "heading": r["title"],
                        "text": "SYNTHETIC "
                        + r["key"]
                        + " procedure, applicability and conclusion independently reviewed for test mechanics only",
                    }
                    for r in items
                ],
                "sources": [{"kind": "record", "id": evidence["id"]}],
                "conclusion": "SYNTHETIC clause evidence graph, not an audit opinion",
                "report_requirement_scope": {
                    "preset_id": pack["id"],
                    "period_start": "2025-04-01",
                    "period_end": "2026-03-31",
                    "items": [
                        {
                            "key": r["key"],
                            "disposition": "REQUIRED",
                            "section_index": index,
                            "supporting_sources": [{"kind": "record", "id": evidence["id"]}],
                            "assessment": "SYNTHETIC explicit source/section mapping for "
                            + r["key"],
                        }
                        for index, r in enumerate(items)
                    ],
                },
            },
        )
        paper = await action(c, h, base, paper, "submit")
        paper = await action(c, manager[0], base, paper, "approve")
        paper = await action(c, partner[0], base, paper, "approve")
        blocks.append(
            {
                "key": "clauses" + str(start),
                "title": "Reviewed CARO matters " + str(start),
                "kind": "working_paper_reference",
                "source_kind": "record",
                "source_id": paper["id"],
                "requirement_keys": [r["key"] for r in items],
            }
        )
    report_prefix = f"/api/v1/regulatory/engagements/{eid}"
    template = await c.post(
        report_prefix + "/report-templates",
        headers=h,
        json={
            "title": "SYNTHETIC CARO numbered matter draft",
            "category": "caro",
            "requirements_pack": pack["id"],
            "company_reporting_scope_id": checked.json()["id"],
            "requirements": [{**r, "disposition": "REQUIRED"} for r in pack["requirements"]],
            "requirements_assessed": True,
            "requirements_basis": "SYNTHETIC every numbered matter mapped to its distinct reviewed section",
            "blocks": blocks,
            "rationale": "SYNTHETIC actual retained clause mappings, no professional qualification",
        },
    )
    assert template.status_code == 201, template.text
    reviewed = await decision(c, reviewer[0], eid, template.json())
    assert reviewed.status_code == 201, reviewed.text
    generated = await c.post(
        report_prefix + "/reports",
        headers=h,
        json={
            "template_id": reviewed.json()["id"],
            "rationale": "SYNTHETIC full numbered inventory and reviewed source graph",
        },
    )
    assert generated.status_code == 201, generated.text
    report = generated.json()
    assert len(report["body"]["requirements_coverage"]["items"]) == 50
    assert report["body"]["company_reporting_scope_id"] == checked.json()["id"]
    exported = await c.get(prefix + "/events/" + report["id"] + "/export?format=xlsx", headers=h)
    assert exported.status_code == 200, exported.text
    book = load_workbook(io.BytesIO(exported.content), read_only=True)
    cells = {
        str(v) for sheet in book.worksheets for row in sheet.values for v in row if v is not None
    }
    assert all(r["key"] in cells for r in pack["requirements"])
    book.close()
    evidence = await action(c, partner[0], base, evidence, "reopen")
    replacement = await c.post(
        base + "/evidence-files/" + evidence["id"],
        headers=h,
        files={
            "file": (
                "revised.txt",
                b"SYNTHETIC changed clause procedures require reassessment",
                "text/plain",
            )
        },
    )
    assert replacement.status_code == 201, replacement.text
    retained = await c.get(prefix + "/events/" + report["id"], headers=h)
    assert retained.json()["freshness"] == "STALE"
    assert retained.json()["body"] == report["body"]
