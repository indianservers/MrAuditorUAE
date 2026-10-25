"""Explicit synthetic contribution/return/bank populations for browser verification."""

import json

from tests.phase4.test_workflows import create
from tests.qa_crud.test_country_workflows import decision, execute, source
from tests.unit.country_workflow_cases import transaction
from tests.unit.test_contribution_source import request
from tests.unit.test_payroll_rule_workflow import pf_fixture
from tests.unit.test_pension_workflow import pension_fixture, scope


async def prepare(c, h, contexts, pension, reviewer):
    from app.core.config import settings

    if settings().environment != "test" or not settings().database_url.endswith(
        "/auditos_country_workflows_test"
    ):
        raise RuntimeError(
            "Contribution browser fixtures require the owned disposable database"
        )
    output = {}
    for country in ("AE", "IN"):
        eid = contexts[country]["engagement"]
        inputs = pension if country == "AE" else contexts[country]["payroll"]
        noun = "pension" if country == "AE" else "payroll"
        derived = await c.post(
            f"/api/v1/intelligence/engagements/{eid}/{noun}-rule-source",
            headers=h,
            json={
                "basis_source_id": inputs["bases"],
                "rule_version_ids": inputs["profiles"],
                "expected_basis_rows": 3,
                "label": "SYNTHETIC contribution settlement rules " + country,
                "assessment": "Explicit synthetic coverage, contribution salary and complete wage-month profile assessment",
            },
        )
        assert derived.status_code == 201, derived.text
        rules = await decision(c, reviewer[0], eid, derived.json())
        assert rules.status_code == 201, rules.text
        parent = await execute(
            c,
            h,
            eid,
            "country-workflow",
            {
                "workflow": "uae-pension-review"
                if country == "AE"
                else "india-payroll-rules",
                "source_ids": {
                    "bases": inputs["bases"],
                    "rules": rules.json()["id"],
                    "reported": inputs["reported"],
                },
                "as_of": "2026-06-30",
                "currency": "AED" if country == "AE" else "INR",
                "title": "SYNTHETIC reviewed settlement contribution parent " + country,
                "rationale": "Independently reviewed synthetic contribution bases and published profiles",
            },
        )
        approved = await decision(c, reviewer[0], eid, parent)
        assert approved.status_code == 201, approved.text
        base = f"/api/v1/engagements/{eid}/audit"
        record = await create(
            c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
        )
        document = await c.post(
            base + "/evidence-files/" + record["id"],
            headers=h,
            files={
                "file": (
                    "SYNTHETIC-due-date-" + country + ".txt",
                    b"SYNTHETIC independent assessed due date: 15 July 2026",
                    "text/plain",
                )
            },
        )
        assert document.status_code == 201, document.text
        control = request(country).model_dump(mode="json")
        total, currency = ("2200.00", "AED") if country == "AE" else ("3600", "INR")
        if country == "AE":
            reported = [
                {
                    key: row[key]
                    for key in (
                        "id",
                        "registration",
                        "subject",
                        "period",
                        "component",
                        "currency",
                        "amount",
                    )
                }
                for row in pension_fixture()[2]
                if row["component"] != "PENSION:GOVERNMENT"
            ]
            for row in reported:
                row["pension_scope"] = json.dumps(scope())
        else:
            reported = pf_fixture()[2]
        expected_ids = {
            row["component"]: "contribution:" + row["id"]
            for row in parent["body"]["rows"]
        }
        links = [
            {
                "id": "A" + str(index),
                "expected_id": expected_ids[row["component"]],
                "reported_id": row["id"],
                "transaction_id": "B1",
                "currency": currency,
                "amount": row["amount"],
                "evidence_reference": "SYNTHETIC-REMITTANCE-ADVICE",
                "rationale": "Independent person and component allocation from synthetic payment advice",
            }
            for index, row in enumerate(reported)
        ]
        sources = {}
        for role, table, rows, totals in (
            ("reported", "obligations", reported, {currency: total}),
            (
                "bank",
                "transactions",
                [
                    transaction(
                        id="B1",
                        amount="-" + total,
                        date="2026-07-15",
                        currency=currency,
                    )
                ],
                {currency: "-" + total},
            ),
            ("allocations", "obligation-allocations", links, {currency: total}),
        ):
            item = await source(
                c,
                h,
                eid,
                rows,
                "SYNTHETIC contribution settlement " + country + " " + role,
                table,
                totals,
            )
            reviewed = await decision(c, reviewer[0], eid, item)
            assert reviewed.status_code == 201, reviewed.text
            sources[role] = reviewed.json()["id"]
        output[country] = {
            "engagement": eid,
            "result": approved.json()["id"],
            "due_date_evidence": document.json()["id"],
            "groups": control["groups"],
            "pension_scope": control["pension_scope"],
            "sources": sources,
            "total": total,
            "currency": currency,
        }
    return output
