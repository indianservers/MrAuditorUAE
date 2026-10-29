"""Real HTTP/DB/storage/processor; antivirus and broker are explicit doubles."""

import io
import os
from copy import deepcopy

import pytest
from openpyxl import load_workbook

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.country_workflow_cases import transaction
from tests.unit.test_payroll_establishment_charges import fixture

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned migrated disposable database required"
)


@pytest.mark.parametrize("withdrawal", ["policy-document", "member-review"])
async def test_establishment_charge_review_expected_remittance_bank_and_staleness(
    environment, monkeypatch, withdrawal
):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "charge-source-reviewer")
    final = await actor(h, "Firm Administrator", "charge-final-reviewer")
    for participant in (reviewer, final):
        await grant(c, h, base, participant)
    prefix = f"/api/v1/intelligence/engagements/{eid}"
    document = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    uploaded = await c.post(
        base + "/evidence-files/" + document["id"],
        headers=h,
        files={
            "file": (
                "SYNTHETIC-charge-policy.txt",
                b"SYNTHETIC assessed minimum and explicit July 15 due date, not law",
                "text/plain",
            )
        },
    )
    assert uploaded.status_code == 201, uploaded.text
    _, tables = fixture()
    for row in tables["rules"]:
        row.pop("source_evidence_version_id")
        row.pop("source_sha256")
    retained = {}
    for role, table_type, totals in [
        ("members", "payroll-charge-members", {"INR": "20000"}),
        ("controls", "payroll-charge-controls", {"INR": "20000"}),
        ("rules", "payroll-charge-rules", {}),
        ("reported", "obligations", {"INR": "500"}),
    ]:
        retained[role] = await source(
            c,
            h,
            eid,
            tables[role],
            "SYNTHETIC charge " + role,
            table_type,
            totals,
            **({"rule_document_version_id": uploaded.json()["id"]} if role == "rules" else {}),
        )
    parameters = dict(
        workflow="india-establishment-charges",
        source_ids={role: obj["id"] for role, obj in retained.items()},
        as_of="2026-06-30",
        currency="INR",
        title="SYNTHETIC establishment charge review",
        rationale="Independent members, establishment wage totals and assessed policy",
    )
    await execute(
        c, h, eid, "country-workflow", parameters, failed="Independently review every member"
    )
    for role, obj in retained.items():
        response = await decision(c, reviewer[0], eid, obj)
        assert response.status_code == 201, response.text
        retained[role] = response.json()
    parameters["source_ids"] = {role: obj["id"] for role, obj in retained.items()}
    result = await execute(c, h, eid, "country-workflow", parameters)
    assert not result["body"]["blocked"] and result["body"]["expected_total"] == "500"
    assert result["body"]["rows"][0]["applied_establishment_minimum"] == "500"
    assert (
        result["body"]["establishment_charge_document_binding"]
        == "RETAINED_DOCUMENT_BYTES_VERIFIED"
    )
    assert (await decision(c, h, eid, result)).status_code == 403
    response = await decision(c, final[0], eid, result)
    assert response.status_code == 201, response.text
    result = response.json()
    exported = await c.get(prefix + f"/events/{result['id']}/export?format=xlsx", headers=h)
    assert exported.status_code == 200, exported.text
    members = list(
        load_workbook(io.BytesIO(exported.content))["Establishment charge members"].values
    )
    assert len(members) == 3
    assert {row[members[0].index("member_source_id")] for row in members[1:]} == {"m1", "m2"}
    assert all(row[members[0].index("member_rounded_charge")] is None for row in members[1:])
    bridge = dict(
        result_id=result["id"],
        due_date_evidence_version_id=uploaded.json()["id"],
        label="SYNTHETIC establishment expected remittance",
        assessment="Independent charge population, due date and expected total",
        groups=[
            dict(
                registration="SYNTHETIC-EST",
                period="2026-06",
                component="PF:ADMINISTRATION",
                expected_rows=1,
                amount="500",
                due_date="2026-07-15",
                due_date_reference="Synthetic reviewed due-date support",
            )
        ],
    )
    wrong = deepcopy(bridge)
    wrong["groups"][0]["amount"] = "1000"
    assert (
        await c.post(prefix + "/contribution-obligation-source", headers=h, json=wrong)
    ).status_code == 422
    response = await c.post(prefix + "/contribution-obligation-source", headers=h, json=bridge)
    assert response.status_code == 201, response.text
    expectation = response.json()
    assert expectation["body"]["allowed_source_roles"] == ["expected"]
    bank = await source(
        c,
        h,
        eid,
        [transaction(id="BANK1", date="2026-07-15", amount="-500", currency="INR")],
        "SYNTHETIC charge bank outflow",
        "transactions",
        {"INR": "-500"},
    )
    allocations = await source(
        c,
        h,
        eid,
        [
            dict(
                id="allocation",
                expected_id=expectation["body"]["rows"][0]["id"],
                reported_id=tables["reported"][0]["id"],
                transaction_id="BANK1",
                currency="INR",
                amount="500",
                evidence_reference="SYNTHETIC bank advice",
                rationale="Independent establishment charge allocation",
            )
        ],
        "SYNTHETIC charge bank allocation",
        "obligation-allocations",
        {"INR": "500"},
    )
    selected = {}
    for role, obj in [
        ("expected", expectation),
        ("reported", retained["reported"]),
        ("bank", bank),
        ("allocations", allocations),
    ]:
        if obj["body"].get("review_status") != "REVIEWED":
            response = await decision(c, reviewer[0], eid, obj)
            assert response.status_code == 201, response.text
            obj = response.json()
        selected[role] = obj["id"]
        if role == "expected":
            expectation = obj
    settlement = await execute(
        c,
        h,
        eid,
        "country-workflow",
        dict(
            workflow="obligation-bank-allocations",
            source_ids=selected,
            as_of="2026-07-31",
            currency="INR",
            title="SYNTHETIC establishment charge bank comparison",
            rationale="Independent expected charge, original report, and allocated bank evidence",
            account="BANK-1",
            obligation_month_start="2026-06",
            obligation_month_end="2026-06",
            settlement_start="2026-07-01",
            bank_payment_sign="debit-negative",
        ),
    )
    assert not settlement["body"]["blocked"] and settlement["body"]["rows"][0]["state"] == "MATCHED"
    before = {obj["id"]: deepcopy(obj["body"]) for obj in (result, expectation, settlement)}
    if withdrawal == "member-review":
        response = await decision(c, reviewer[0], eid, retained["members"], "reject")
    else:
        response = await c.post(
            base + "/evidence-files/" + document["id"],
            headers=h,
            files={
                "file": (
                    "SYNTHETIC-replacement-policy.txt",
                    b"SYNTHETIC changed assessed policy",
                    "text/plain",
                )
            },
        )
    assert response.status_code == 201, response.text
    for identifier, body in before.items():
        stale = (await c.get(prefix + "/events/" + identifier, headers=h)).json()
        assert stale["freshness"] == "STALE" and stale["body"] == body
    assert (await decision(c, final[0], eid, result)).status_code == 409
