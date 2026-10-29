"""Real HTTP, DB, storage and processor; scanner and dispatch are explicit doubles."""

import io
import os
from copy import deepcopy
from decimal import Decimal

import pytest
from openpyxl import load_workbook

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.country_workflow_cases import transaction
from tests.unit.test_payroll_basis_proration import fixture

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned migrated disposable database required"
)


@pytest.mark.parametrize("withdrawal", ["review", "original-file", "policy-document"])
async def test_dated_wages_to_contributions_remittance_bank_and_recursive_staleness(
    environment, monkeypatch, withdrawal
):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "dated-basis-source-reviewer")
    final = await actor(h, "Firm Administrator", "dated-basis-final-reviewer")
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
                "SYNTHETIC-assessed-ceiling.txt",
                b"SYNTHETIC supplied wage options and separately assessed due dates",
                "text/plain",
            )
        },
    )
    assert uploaded.status_code == 201, uploaded.text
    _, tables = fixture()
    for rule in tables["rules"]:
        rule.pop("source_sha256")
        rule.pop("source_evidence_version_id")
    retained = {}
    for role, table_type in [
        ("segments", "payroll-basis-segments"),
        ("rules", "payroll-cap-rules"),
        ("controls", "payroll-bases"),
    ]:
        rows = tables[role]
        total = (
            str(sum((Decimal(r["amount"]) for r in rows), Decimal(0))) if role != "rules" else None
        )
        retained[role] = await source(
            c,
            h,
            eid,
            rows,
            "SYNTHETIC dated PF " + role,
            table_type,
            {"INR": total} if total is not None else {},
            **({"rule_document_version_id": uploaded.json()["id"]} if role == "rules" else {}),
        )
    parameters = dict(
        workflow="india-payroll-basis-proration",
        source_ids={r: s["id"] for r, s in retained.items()},
        as_of="2026-09-30",
        currency="INR",
        title="SYNTHETIC dated wage-basis controls",
        rationale="Check original calendar segments and separately assessed monthly bases",
    )
    await execute(
        c, h, eid, "country-workflow", parameters, failed="Independently review every wage"
    )
    for role, item in retained.items():
        reviewed = await decision(c, reviewer[0], eid, item)
        assert reviewed.status_code == 201, reviewed.text
        retained[role] = reviewed.json()
    parameters["source_ids"] = {r: s["id"] for r, s in retained.items()}
    result = await execute(c, h, eid, "country-workflow", parameters)
    assert result["body"]["monthly_basis_complete"] and not result["body"]["blocked"]
    assert (await decision(c, h, eid, result)).status_code == 403
    source_request = dict(
        result_id=result["id"],
        expected_rows=9,
        control_total="129333.31",
        label="SYNTHETIC monthly post-ceiling wages",
        assessment="Independent full monthly component controls checked",
    )
    endpoint = prefix + "/prorated-payroll-basis-source"
    assert (await c.post(endpoint, headers=h, json=source_request)).status_code == 409
    reviewed = await decision(c, final[0], eid, result)
    assert reviewed.status_code == 201, reviewed.text
    result = reviewed.json()
    source_request["result_id"] = result["id"]
    assert (
        await c.post(endpoint, headers=h, json={**source_request, "control_total": "0"})
    ).status_code == 422
    response = await c.post(endpoint, headers=h, json=source_request)
    assert response.status_code == 201, response.text
    monthly_source = response.json()
    assert (await decision(c, h, eid, monthly_source)).status_code == 403
    response = await decision(c, reviewer[0], eid, monthly_source)
    assert response.status_code == 201, response.text
    monthly_source = response.json()
    export = await c.get(prefix + f"/events/{result['id']}/export?format=xlsx", headers=h)
    assert export.status_code == 200, export.text
    exported = list(load_workbook(io.BytesIO(export.content))["Payroll basis segments"].values)
    assert len(exported) == 19
    assert exported[-1][exported[0].index("segment_end")] == "2026-09-30"
    amounts = {
        "SYN-A": {"PF:EMPLOYEE": "1120.00", "PF:EPS": "777.47", "PF:EMPLOYER": "342.53"},
        "SYN-B": {"PF:EMPLOYEE": "2400.00", "PF:EPS": "777.47", "PF:EMPLOYER": "1622.53"},
        "SYN-C": {"PF:EMPLOYEE": "2080.00", "PF:EPS": "1443.87", "PF:EMPLOYER": "636.13"},
    }
    rates, reported = [], []
    for row in tables["controls"]:
        eps = row["component"] == "PF:EPS"
        rates.append(
            dict(
                id="rate:" + row["id"],
                rule_group=row["rule_group"],
                component=row["component"],
                jurisdiction=row["jurisdiction"],
                effective_from="2026-09-01",
                effective_to="2026-09-30",
                formula="employer-minus-eps" if row["component"] == "PF:EMPLOYER" else "rate",
                rate="0.0833" if eps else "0.12",
                rounding="paise",
                source_url="https://synthetic.invalid/rate",
                source_version="SYNTHETIC-1",
                evidence_reference="SYN-RATE",
                applicability_review="Synthetic independently assessed whole-month contribution rate",
            )
        )
        reported.append(
            {
                k: row[k]
                for k in ("id", "registration", "subject", "period", "component", "currency")
            }
            | {"amount": amounts[row["subject"]][row["component"]]}
        )
    rate_source = await source(
        c,
        h,
        eid,
        rates,
        "SYNTHETIC uncapped monthly rates",
        "payroll-rules",
        {},
        rule_document_version_id=uploaded.json()["id"],
    )
    reported_source = await source(
        c,
        h,
        eid,
        reported,
        "SYNTHETIC independent contribution return",
        "obligations",
        {"INR": "11200.00"},
    )
    reviewed_rate = await decision(c, reviewer[0], eid, rate_source)
    assert reviewed_rate.status_code == 201, reviewed_rate.text
    reviewed_reported = await decision(c, reviewer[0], eid, reported_source)
    assert reviewed_reported.status_code == 201, reviewed_reported.text
    reported_source = reviewed_reported.json()
    monthly_params = {
        **parameters,
        "workflow": "india-payroll-rules",
        "source_ids": {
            "bases": monthly_source["id"],
            "rules": reviewed_rate.json()["id"],
            "reported": reported_source["id"],
        },
    }
    monthly = await execute(c, h, eid, "country-workflow", monthly_params)
    assert not monthly["body"]["blocked"] and all(
        r["state"] == "MATCHED" for r in monthly["body"]["rows"]
    )
    response = await decision(c, final[0], eid, monthly)
    assert response.status_code == 201, response.text
    monthly = response.json()
    contribution_request = dict(
        result_id=monthly["id"],
        due_date_evidence_version_id=uploaded.json()["id"],
        label="SYNTHETIC contribution expectations",
        assessment="Independent original due date and group remittance controls",
        groups=[
            dict(
                registration="SYN-EST",
                period="2026-09",
                component=component,
                expected_rows=3,
                amount=amount,
                due_date="2026-10-15",
                due_date_reference="SYNTHETIC-ASSESSED-DATE",
            )
            for component, amount in [
                ("PF:EMPLOYEE", "5600.00"),
                ("PF:EPS", "2998.81"),
                ("PF:EMPLOYER", "2601.19"),
            ]
        ],
    )
    response = await c.post(
        prefix + "/contribution-obligation-source", headers=h, json=contribution_request
    )
    assert response.status_code == 201, response.text
    expectation = response.json()
    bank = await source(
        c,
        h,
        eid,
        [transaction(id="BANK1", date="2026-10-15", amount="-11200.00", currency="INR")],
        "SYNTHETIC bank outflow",
        "transactions",
        {"INR": "-11200.00"},
    )
    indexed = {(r["subject"], r["component"]): r["id"] for r in expectation["body"]["rows"]}
    links = [
        dict(
            id="allocation:" + r["id"],
            expected_id=indexed[(r["subject"], r["component"])],
            reported_id=r["id"],
            transaction_id="BANK1",
            currency="INR",
            amount=r["amount"],
            evidence_reference="SYN-ADVICE",
            rationale="Independent employee and contribution allocation to bank outflow",
        )
        for r in reported
    ]
    allocations = await source(
        c,
        h,
        eid,
        links,
        "SYNTHETIC bank remittance allocations",
        "obligation-allocations",
        {"INR": "11200.00"},
    )
    selected = {}
    for role, item in [
        ("expected", expectation),
        ("reported", reported_source),
        ("bank", bank),
        ("allocations", allocations),
    ]:
        if item["body"].get("review_status") == "REVIEWED":
            reviewed_item = item
        else:
            response = await decision(c, reviewer[0], eid, item)
            assert response.status_code == 201, response.text
            reviewed_item = response.json()
        selected[role] = reviewed_item["id"]
        if role == "expected":
            expectation = reviewed_item
    settlement = await execute(
        c,
        h,
        eid,
        "country-workflow",
        dict(
            workflow="obligation-bank-allocations",
            source_ids=selected,
            as_of="2026-10-31",
            currency="INR",
            title="SYNTHETIC dated-basis bank remittance",
            rationale="Independent reported contributions, due-date assessment and bank allocations",
            account="BANK-1",
            obligation_month_start="2026-09",
            obligation_month_end="2026-09",
            settlement_start="2026-10-01",
            bank_payment_sign="debit-negative",
        ),
    )
    assert not settlement["body"]["blocked"]
    assert all(r["state"] == "MATCHED" for r in settlement["body"]["rows"])
    before = {
        obj["id"]: deepcopy(obj["body"])
        for obj in [result, monthly_source, monthly, expectation, settlement]
    }
    original = retained["segments"]
    if withdrawal == "review":
        response = await decision(c, reviewer[0], eid, original, "reject")
        assert response.status_code == 201, response.text
    else:
        evidence = next(d for d in original["dependencies"] if d["type"] == "evidence")
        response = await c.post(
            base
            + "/evidence-files/"
            + (document["id"] if withdrawal == "policy-document" else evidence["record_id"]),
            headers=h,
            files={
                "file": (
                    "SYNTHETIC-corrected-wages.txt",
                    b"SYNTHETIC changed original wage population",
                    "text/plain",
                )
            },
        )
        assert response.status_code == 201, response.text
    for identifier, body in before.items():
        stale = (await c.get(prefix + "/events/" + identifier, headers=h)).json()
        assert stale["freshness"] == "STALE" and stale["body"] == body
    assert (await decision(c, final[0], eid, result)).status_code == 409
