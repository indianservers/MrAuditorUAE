"""Reviewed tax transactions become identity-preserving split cash obligations."""

import io
import json
import os

import pytest
from openpyxl import load_workbook

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_dues_allocations import parameters
from tests.unit.test_withholding_obligations import controls, records, settlement

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable DB required"
)


async def retain_withholding(c, h, eid, base, reviewer, legal_role="deductor"):
    record = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    uploaded = await c.post(
        base + "/evidence-files/" + record["id"],
        headers=h,
        files={
            "file": (
                "SYNTHETIC withholding assessment.json",
                json.dumps(
                    {
                        "classification": "SYNTHETIC_RULE_ASSESSMENT_NOT_LEGAL_QUALIFICATION",
                        "coverage": ["2026-04-01", "2027-03-31"],
                        "due_date": "2026-06-30",
                    }
                ).encode(),
                "application/json",
            )
        },
    )
    assert uploaded.status_code == 201, uploaded.text
    sources = {}
    for purpose in ("expected", "reported"):
        population = records(purpose, legal_role)
        for row in population:
            row.update(
                assessment_evidence_version_id=uploaded.json()["id"],
                assessment_sha256=uploaded.json()["sha256"],
            )
        prepared = await source(
            c,
            h,
            eid,
            population,
            "SYNTHETIC " + purpose + " tax observations",
            "withholding-records",
            {"INR": "1080"},
        )
        approved = await decision(c, reviewer[0], eid, prepared)
        assert approved.status_code == 201, approved.text
        sources[purpose] = approved.json()
    return sources, record


async def prepare_withholding_settlement(c, h, eid, base, reviewer, legal_role="deductor"):
    parents, assessment = await retain_withholding(c, h, eid, base, reviewer, legal_role)
    prefix = f"/api/v1/intelligence/engagements/{eid}"
    bridges = {}
    for purpose, parent in parents.items():
        data = controls(purpose=purpose, legal_role=legal_role).model_dump(mode="json")
        response = await c.post(
            prefix + f"/events/{parent['id']}/withholding-obligation-source", headers=h, json=data
        )
        assert response.status_code == 201, response.text
        bridge = response.json()
        assert bridge["body"]["review_status"] == "UNVERIFIED"
        assert bridge["body"]["source_sha256"] == parent["body"]["evidence_sha256"]
        assert bridge["body"]["allowed_source_roles"] == [purpose]
        assert (await decision(c, h, eid, bridge)).status_code == 403
        approved = await decision(c, reviewer[0], eid, bridge)
        assert approved.status_code == 201, approved.text
        bridges[purpose] = approved.json()
    population = settlement(legal_role)
    for movement in population["bank"]:
        movement["reference"] += "-" + legal_role
    sources = {role: bridge["id"] for role, bridge in bridges.items()}
    for role, table_type, totals in (
        ("bank", "transactions", {"INR": "-180"}),
        ("allocations", "obligation-allocations", {"INR": "180"}),
    ):
        prepared = await source(
            c, h, eid, population[role], "SYNTHETIC split withholding " + role, table_type, totals
        )
        approved = await decision(c, reviewer[0], eid, prepared)
        assert approved.status_code == 201, approved.text
        sources[role] = approved.json()["id"]
    args = {
        **parameters(),
        "source_ids": sources,
        "currency": "INR",
        "obligation_month_start": "2026-05",
        "obligation_month_end": "2026-05",
    }
    return parents, bridges, assessment, args


@pytest.mark.parametrize("legal_role", ["deductor", "collector"])
async def test_split_withholding_bank_settlement_review_export_and_proof_replacement(
    environment, monkeypatch, legal_role
):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "withholding-split-reviewer")
    await grant(c, h, base, reviewer)
    parents, bridges, assessment, args = await prepare_withholding_settlement(
        c, h, eid, base, reviewer, legal_role
    )
    result = await execute(c, h, eid, "country-workflow", args)
    assert result["body"]["exception_count"] == 0
    obligations = [row for row in result["body"]["rows"] if row["kind"] == "obligation"]
    assert len(obligations) == 2 and obligations[1]["outstanding_amount"] == "0"
    assert len(obligations[1]["payment_allocations"]) == 2
    assert (
        obligations[0]["withholding_scope"]["transaction_reference"]
        != obligations[1]["withholding_scope"]["transaction_reference"]
    )
    assert (await decision(c, h, eid, result)).status_code == 403
    approved = await decision(c, reviewer[0], eid, result)
    assert approved.status_code == 201, approved.text
    prefix = f"/api/v1/intelligence/engagements/{eid}"
    # A separate workpaper cannot spend the same cash a second time.
    competing = await execute(c, h, eid, "country-workflow", args)
    blocked = await decision(c, reviewer[0], eid, competing)
    assert blocked.status_code == 409 and "OVERALLOCATED" in blocked.text
    status = await c.get(prefix + f"/events/{competing['id']}/bank-cash-status", headers=h)
    assert status.status_code == 200, status.text
    assert status.json()["state"] == "UNRESERVED"
    assert status.json()["related_reviews"][0]["root_id"] == approved.json()["root_id"]
    exported = await c.get(
        prefix + f"/events/{approved.json()['id']}/export?format=xlsx", headers=h
    )
    assert exported.status_code == 200
    workbook = load_workbook(io.BytesIO(exported.content), read_only=True)
    values = list(workbook["Rows"].values)
    assert "withholding_scope" in values[0]
    assert '"tax_year_start": "2026-04-01"' in values[1][values[0].index("withholding_scope")]
    workbook.close()
    # A source cannot establish both sides merely by changing its declared purpose.
    copied = await c.post(
        prefix + f"/events/{parents['expected']['id']}/withholding-obligation-source",
        headers=h,
        json=controls(purpose="reported", legal_role=legal_role).model_dump(mode="json"),
    )
    assert copied.status_code == 201, copied.text
    copied_review = await decision(c, reviewer[0], eid, copied.json())
    assert copied_review.status_code == 201
    await execute(
        c,
        h,
        eid,
        "country-workflow",
        {**args, "source_ids": {**args["source_ids"], "reported": copied_review.json()["id"]}},
        failed="same evidence version",
    )
    # Cutoff is part of the preparation contract, not an informal date hint.
    await execute(c, h, eid, "country-workflow", {**args, "as_of": "2026-07-01"}, failed="cutoff")
    replaced = await c.post(
        base + "/evidence-files/" + assessment["id"],
        headers=h,
        files={
            "file": (
                "SYNTHETIC changed tax assessment.json",
                b'{"classification":"SYNTHETIC_REPLACEMENT_REQUIRES_REVIEW"}',
                "application/json",
            )
        },
    )
    assert replaced.status_code == 201
    for item in [*bridges.values(), approved.json()]:
        response = await c.get(prefix + f"/events/{item['id']}", headers=h)
        assert response.status_code == 200 and response.json()["freshness"] == "STALE"
    assert (await decision(c, reviewer[0], eid, result)).status_code == 409
    # Source staleness retains the earlier cash claim. An independent reviewer
    # explicitly withdraws it without pretending to revalidate stale amounts.
    withdraw_url = prefix + f"/events/{approved.json()['id']}/withdraw-bank-cash"
    withdrawal = {
        "action": "reject",
        "expected_version": approved.json()["version"],
        "comments": "Synthetic evidence replaced; release the prior cash claim",
    }
    assert (await c.post(withdraw_url, headers=h, json=withdrawal)).status_code == 403
    withdrawn = await c.post(withdraw_url, headers=reviewer[0], json=withdrawal)
    assert withdrawn.status_code == 201, withdrawn.text
    assert withdrawn.json()["body"]["bank_consumption_review"]["status"] == "WITHDRAWN"
    assert (await c.post(withdraw_url, headers=reviewer[0], json=withdrawal)).status_code == 409
    historical = await c.get(prefix + f"/events/{approved.json()['id']}", headers=h)
    assert historical.json()["body"]["review_status"] == "REVIEWED"
