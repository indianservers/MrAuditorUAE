"""Actual HTTP/DB/storage/processor; scanner and dispatch are explicit doubles."""

import os
from copy import deepcopy

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.unit.country_workflow_cases import transaction
from tests.unit.test_savings_scheme import fixture, request

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned migrated disposable database required"
)


@pytest.mark.parametrize(
    "withdrawal",
    ["enrolment-document", "policy-document", "fund-source-review", "fund-original-file"],
)
async def test_savings_contributions_original_fund_observations_bank_and_scoped_staleness(
    environment, monkeypatch, withdrawal
):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    reviewer = await actor(h, "Firm Administrator", "savings-source-reviewer")
    final = await actor(h, "Firm Administrator", "savings-final-reviewer")
    for member in (reviewer, final):
        await grant(c, h, base, member)
    prefix = f"/api/v1/intelligence/engagements/{eid}"
    documents = {}
    for purpose in ["enrolment", "policy", "due-date"]:
        record = await create(
            c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
        )
        response = await c.post(
            base + "/evidence-files/" + record["id"],
            headers=h,
            files={
                "file": (
                    f"SYNTHETIC-savings-{purpose}.txt",
                    f"SYNTHETIC retained {purpose} assessment only".encode(),
                    "text/plain",
                )
            },
        )
        assert response.status_code == 201, response.text
        documents[purpose] = (record, response.json())
    _, tables = fixture()
    for row in tables["bases"]:
        row.pop("enrolment_evidence_version_id")
        row.pop("enrolment_sha256")
    for row in tables["rules"]:
        row.pop("source_evidence_version_id")
        row.pop("source_sha256")
    selected = {
        "bases": await source(
            c,
            h,
            eid,
            tables["bases"],
            "SYNTHETIC enrolled savings wages",
            "savings-bases",
            {"AED": "28000"},
            savings_enrolment_document_version_id=documents["enrolment"][1]["id"],
        ),
        "rules": await source(
            c,
            h,
            eid,
            tables["rules"],
            "SYNTHETIC assessed savings policies",
            "savings-rules",
            {},
            rule_document_version_id=documents["policy"][1]["id"],
        ),
        "reported": await source(
            c,
            h,
            eid,
            tables["reported"],
            "SYNTHETIC original fund observations",
            "savings-reported",
            {"AED": "1415.90"},
        ),
    }
    parameters = dict(
        workflow="uae-savings-review",
        source_ids={role: obj["id"] for role, obj in selected.items()},
        as_of="2026-06-30",
        currency="AED",
        title="SYNTHETIC savings contributions and fund observations",
        rationale="Independent enrolment, assessed wages, rate policies and original fund statement controls",
    )
    await execute(
        c, h, eid, "country-workflow", parameters, failed="Independently review every savings"
    )
    for role, obj in selected.items():
        response = await decision(c, reviewer[0], eid, obj)
        assert response.status_code == 201, response.text
        selected[role] = response.json()
    parameters["source_ids"] = {role: obj["id"] for role, obj in selected.items()}
    result = await execute(c, h, eid, "country-workflow", parameters)
    assert result["body"]["savings_document_binding"] == "RETAINED_DOCUMENT_BYTES_VERIFIED"
    assert not result["body"]["blocked"] and result["body"]["expected_total"] == "1415.90"
    assert (await decision(c, h, eid, result)).status_code == 403
    response = await decision(c, final[0], eid, result)
    assert response.status_code == 201, response.text
    result = response.json()
    expected_request = request().model_dump(mode="json")
    expected_request.update(
        result_id=result["id"], due_date_evidence_version_id=documents["due-date"][1]["id"]
    )
    wrong = {
        **expected_request,
        "groups": [
            {**expected_request["groups"][0], "fund_id": None},
            expected_request["groups"][1],
        ],
    }
    assert (
        await c.post(prefix + "/contribution-obligation-source", headers=h, json=wrong)
    ).status_code == 422
    response = await c.post(
        prefix + "/contribution-obligation-source", headers=h, json=expected_request
    )
    assert response.status_code == 201, response.text
    expected = response.json()
    reported_request = dict(
        source_id=selected["reported"]["id"],
        expected_rows=4,
        control_total="1415.90",
        label="SYNTHETIC preserved fund remittance observations",
        assessment="Independent original fund participant population and amount controls",
    )
    assert (
        await c.post(
            prefix + "/savings-reported-obligation-source",
            headers=h,
            json={**reported_request, "control_total": "0"},
        )
    ).status_code == 422
    response = await c.post(
        prefix + "/savings-reported-obligation-source", headers=h, json=reported_request
    )
    assert response.status_code == 201, response.text
    reported = response.json()
    assert reported["body"]["allowed_source_roles"] == ["reported"]
    assert all(r["payment_date"] is None for r in reported["body"]["rows"])
    assert (await decision(c, h, eid, reported)).status_code == 403
    bank = await source(
        c,
        h,
        eid,
        [transaction(id="B1", date="2026-07-15", amount="-1415.90")],
        "SYNTHETIC savings bank outflow",
        "transactions",
        {"AED": "-1415.90"},
    )
    expected_ids = {r["subject"]: r["id"] for r in expected["body"]["rows"]}
    links = [
        dict(
            id="LINK-" + r["subject"],
            expected_id=expected_ids[r["subject"]],
            reported_id=r["id"],
            transaction_id="B1",
            currency="AED",
            amount=r["amount"],
            evidence_reference="SYN-FUND-REMITTANCE-ADVICE",
            rationale="Independent employee membership and fund coverage allocation to bank cash",
        )
        for r in reported["body"]["rows"]
    ]
    allocations = await source(
        c,
        h,
        eid,
        links,
        "SYNTHETIC fund bank allocations",
        "obligation-allocations",
        {"AED": "1415.90"},
    )
    ids = {}
    for role, item in [
        ("expected", expected),
        ("reported", reported),
        ("bank", bank),
        ("allocations", allocations),
    ]:
        response = await decision(c, reviewer[0], eid, item)
        assert response.status_code == 201, response.text
        item = response.json()
        ids[role] = item["id"]
        if role == "expected":
            expected = item
        if role == "reported":
            reported = item
    settlement_parameters = dict(
        workflow="obligation-bank-allocations",
        source_ids=ids,
        as_of="2026-07-31",
        currency="AED",
        account="BANK-1",
        obligation_month_start="2026-06",
        obligation_month_end="2026-06",
        settlement_start="2026-07-01",
        bank_payment_sign="debit-negative",
        title="SYNTHETIC savings basic bank settlement",
        rationale="Separate expected contributions, original fund observations and independent bank cash",
    )
    settlement = await execute(c, h, eid, "country-workflow", settlement_parameters)
    assert not settlement["body"]["blocked"] and all(
        r["state"] == "MATCHED" for r in settlement["body"]["rows"]
    )
    wrong_purpose = {
        **settlement_parameters,
        "source_ids": {**ids, "expected": ids["reported"], "reported": ids["expected"]},
    }
    await execute(c, h, eid, "country-workflow", wrong_purpose, failed="only expected remittances")
    before = {obj["id"]: deepcopy(obj["body"]) for obj in [result, expected, reported, settlement]}
    if withdrawal.endswith("document"):
        record = documents[withdrawal.split("-")[0]][0]
    elif withdrawal == "fund-original-file":
        receipt = next(d for d in selected["reported"]["dependencies"] if d["type"] == "evidence")
        record = {"id": receipt["record_id"]}
    else:
        response = await decision(c, reviewer[0], eid, selected["reported"], "reject")
        assert response.status_code == 201, response.text
        record = None
    if record:
        response = await c.post(
            base + "/evidence-files/" + record["id"],
            headers=h,
            files={
                "file": (
                    "SYNTHETIC-savings-correction.txt",
                    b"SYNTHETIC changed original supporting facts",
                    "text/plain",
                )
            },
        )
        assert response.status_code == 201, response.text
    for identifier, saved in before.items():
        current = (await c.get(prefix + "/events/" + identifier, headers=h)).json()
        wanted = (
            "CURRENT"
            if identifier == reported["id"] and withdrawal.endswith("document")
            else "STALE"
        )
        assert current["freshness"] == wanted and current["body"] == saved
    assert (await decision(c, final[0], eid, result)).status_code == 409
