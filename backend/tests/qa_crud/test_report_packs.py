"""Actual VAT sources through a preset-bound reviewed report and stale history."""

import io
import os
from copy import deepcopy

import pytest
from openpyxl import load_workbook

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_vat_box_scope import full_filed_boxes
from tests.unit.test_vat_ecommerce import split_rows
from tests.unit.test_vat_emirates import detailed_rows

pytestmark = pytest.mark.skipif(os.getenv("INTEGRATION_TESTS") != "1", reason="Dedicated test DB")


@pytest.mark.parametrize("layout", ["aggregate-14", "emirate-20", "ecommerce-20"])
async def test_vat_preset_requires_complete_reviewed_comparison_and_preserves_stale_report(
    environment, monkeypatch, layout
):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    reviewer = await actor(h, "Firm Administrator", "preset-reviewer")
    await grant(c, h, base, reviewer)
    prefix = f"/api/v1/regulatory/engagements/{eid}"
    presets = (await c.get(prefix + "/report-presets", headers=h)).json()
    assert presets["country"] == "AE" and len(presets["items"]) == 3
    pack = next(p for p in presets["items"] if p["layout"] == layout)
    rows = (
        split_rows()
        if layout == "ecommerce-20"
        else detailed_rows()
        if layout == "emirate-20"
        else full_filed_boxes()
    )
    ids, originals = {}, {}
    for role in ("books", "return"):
        records = [{**row, "id": role + "-" + row["box"]} for row in rows]
        prepared = await source(
            c, h, eid, records, "SYNTHETIC preset " + role, "return-boxes", {"AED": "230"}
        )
        checked = await decision(c, reviewer[0], eid, prepared)
        assert checked.status_code == 201, checked.text
        originals[role] = checked.json()
        ids[role] = checked.json()["id"]
    comparison = await execute(
        c,
        h,
        eid,
        "country-workflow",
        dict(
            workflow="uae-vat-return",
            source_ids=ids,
            vat201_layout=layout,
            required_boxes=pack["required_boxes"],
            currency="AED",
            as_of="2026-06-30",
            title="SYNTHETIC complete VAT201 comparison",
            rationale="Independent explicit book and return populations",
        ),
    )
    checked = await decision(c, reviewer[0], eid, comparison)
    assert checked.status_code == 201, checked.text
    data = dict(
        title="SYNTHETIC VAT201 preset report",
        category="vat",
        rationale="Synthetic operational report only, not filing qualification",
        requirements_pack=pack["id"],
        requirements=[{**r, "disposition": "REQUIRED"} for r in pack["requirements"]],
        requirements_assessed=True,
        requirements_basis="Synthetic explicit box scope and independent reviewed comparison",
        blocks=[
            dict(
                key="vat",
                title="Reviewed VAT201 comparison",
                kind="reconciliation",
                source_kind="intelligence",
                source_id=checked.json()["id"],
                requirement_keys=[r["key"] for r in pack["requirements"]],
            )
        ],
    )
    missing = await c.post(
        prefix + "/report-templates",
        headers=h,
        json={**data, "requirements": data["requirements"][:-1]},
    )
    assert missing.status_code == 422
    response = await c.post(prefix + "/report-templates", headers=h, json=data)
    assert response.status_code == 201, response.text
    template = response.json()
    assert (await decision(c, h, eid, template)).status_code == 403
    approved = await decision(c, reviewer[0], eid, template)
    assert approved.status_code == 201, approved.text
    generated = await c.post(
        prefix + "/reports",
        headers=h,
        json={
            "template_id": approved.json()["id"],
            "rationale": "Synthetic source-pinned unsigned report generation",
        },
    )
    assert generated.status_code == 201, generated.text
    report = generated.json()
    assert report["body"]["requirements_coverage"]["requirements_pack"]["sha256"] == pack["sha256"]
    assert not report["body"]["requirements_coverage"]["statutory_completeness_qualified"]
    event_prefix = f"/api/v1/intelligence/engagements/{eid}/events/"
    exported = await c.get(event_prefix + report["id"] + "/export?format=xlsx", headers=h)
    assert exported.status_code == 200, exported.text
    book = load_workbook(io.BytesIO(exported.content))
    assert any(pack["id"] in [str(v) for v in row] for sheet in book for row in sheet.values)
    wrong_pack = next(p for p in presets["items"] if p["layout"] != layout)
    wrong = await c.post(
        prefix + "/report-templates",
        headers=h,
        json={
            **data,
            "requirements_pack": wrong_pack["id"],
            "requirements": [{**r, "disposition": "REQUIRED"} for r in wrong_pack["requirements"]],
            "blocks": [
                {
                    **data["blocks"][0],
                    "requirement_keys": [r["key"] for r in wrong_pack["requirements"]],
                }
            ],
        },
    )
    assert wrong.status_code == 201, wrong.text
    assert (await decision(c, reviewer[0], eid, wrong.json())).status_code == 409
    historical = deepcopy(report["body"])
    assert (await decision(c, reviewer[0], eid, originals["books"], "reject")).status_code == 201
    stale = await c.get(event_prefix + report["id"], headers=h)
    assert stale.json()["freshness"] == "STALE" and stale.json()["body"] == historical


async def test_uae_preset_is_not_available_for_india(environment):
    c = environment
    h, eid, _ = await india_context(c)
    prefix = f"/api/v1/regulatory/engagements/{eid}"
    response = await c.get(prefix + "/report-presets", headers=h)
    assert response.status_code == 200 and response.json()["country"] == "IN"
    assert len(response.json()["items"]) == 2
    assert all(p["category"] == "india-tax-audit" for p in response.json()["items"])
    from app.modules.regulatory.report_packs import manifest

    pack = manifest("uae-vat201-review:aggregate-14/1")
    response = await c.post(
        prefix + "/report-templates",
        headers=h,
        json=dict(
            title="SYNTHETIC wrong-country report",
            category="vat",
            rationale="Synthetic country-isolation rejection fixture",
            requirements_pack=pack["id"],
            requirements=pack["requirements"],
            blocks=[
                dict(
                    key="draft",
                    title="Synthetic unassessed draft",
                    kind="narrative",
                    text="Synthetic draft without mapped sources",
                )
            ],
        ),
    )
    assert response.status_code == 422 and "country" in response.text
