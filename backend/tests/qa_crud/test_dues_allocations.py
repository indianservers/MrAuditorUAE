"""Native WPS/ECR reporting plus independent bank evidence, reviews and lineage.

Scanner and queue dispatch are doubles; API, object store, DB and processor are real.
Dates and expected amounts are fictional assessments, not qualified legal rules.
"""

import os
from decimal import Decimal

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.native_source_examples import SIF, SIF_FILENAME
from tests.unit.test_dues_allocations import example, parameters
from tests.unit.test_india_ecr_source import ECR

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable database required"
)


def declared_expected(country):
    records = (
        [
            ("12345678901234", "SALARY", "1100", "wps:1"),
            ("12345678901235", "SALARY", "400", "wps:2"),
        ]
        if country == "AE"
        else [
            ("100000000001", "PF:EMPLOYEE", "1800", "ecr:1:PF:EMPLOYEE"),
            ("100000000001", "PF:EPS", "1250", "ecr:1:PF:EPS"),
            ("100000000001", "PF:EMPLOYER", "550", "ecr:1:PF:EMPLOYER"),
            ("100000000002", "PF:EMPLOYEE", "1200", "ecr:2:PF:EMPLOYEE"),
            ("100000000002", "PF:EPS", "0", "ecr:2:PF:EPS"),
            ("100000000002", "PF:EMPLOYER", "1200", "ecr:2:PF:EMPLOYER"),
            ("100000000002", "PF:ADVANCE_REFUND", "100", "ecr:2:PF:ADVANCE_REFUND"),
        ]
    )
    currency = "AED" if country == "AE" else "INR"
    expected = [
        {
            "id": f"E{index}",
            "registration": "1234567890123" if country == "AE" else "SYNTHETIC-EPFO-001",
            "subject": subject,
            "component": component,
            "period": "2026-06",
            "amount": amount,
            "currency": currency,
            "due_date": "2026-06-29",
            "payment_date": None,
        }
        for index, (subject, component, amount, _) in enumerate(records, 1)
    ]
    return records, expected


async def test_whitespace_in_india_component_does_not_activate_it_in_uae(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    reviewer = await actor(h, "Firm Administrator", "country-component-reviewer")
    await grant(c, h, base, reviewer)
    population = example(component="pf : employee")
    kinds = {
        "expected": "obligations",
        "reported": "obligations",
        "bank": "transactions",
        "allocations": "obligation-allocations",
    }
    selected = {}
    for role, rows in population.items():
        total = sum(Decimal(row["amount"]) for row in rows)
        imported = await source(
            c,
            h,
            eid,
            rows,
            "SYNTHETIC whitespace country scope " + role,
            kinds[role],
            {"AED": str(total)},
        )
        reviewed = await decision(c, reviewer[0], eid, imported)
        assert reviewed.status_code == 201, reviewed.text
        selected[role] = reviewed.json()["id"]
    await execute(
        c,
        h,
        eid,
        "country-workflow",
        {**parameters(), "source_ids": selected},
        failed="Indian domestic",
    )


@pytest.mark.parametrize(
    "country,currency,total,tail", [("AE", "AED", "1500", "10"), ("IN", "INR", "6100", "100")]
)
async def test_native_reporting_independent_allocated_bank_and_replacement(
    environment, monkeypatch, country, currency, total, tail
):
    c = environment
    double_boundaries(monkeypatch)
    if country == "AE":
        h, _, eid, base = await setup(c)
    else:
        h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "dues-allocation-reviewer")
    await grant(c, h, base, reviewer)
    document = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    content, filename, media = (
        (SIF, SIF_FILENAME, "text/csv")
        if country == "AE"
        else (ECR, "SYNTHETIC-ECR.txt", "text/plain")
    )
    uploaded = await c.post(
        base + "/evidence-files/" + document["id"],
        headers=h,
        files={"file": (filename, content, media)},
    )
    assert uploaded.status_code == 201, uploaded.text
    reported = await execute(
        c,
        h,
        eid,
        "workflow-source",
        {
            "evidence_version_id": uploaded.json()["id"],
            "file_format": "uae-wps-sif" if country == "AE" else "india-epfo-ecr",
            "table_type": "obligations",
            "label": "SYNTHETIC independently retained reported file",
            "expected_rows": 2 if country == "AE" else 7,
            "control_totals": {currency: total},
            **(
                {
                    "employer_registration": "SYNTHETIC-EPFO-001",
                    "obligation_period": "2026-06",
                    "expected_members": 2,
                }
                if country == "IN"
                else {}
            ),
        },
    )
    records, expected_rows = declared_expected(country)
    expected = await source(
        c,
        h,
        eid,
        expected_rows,
        "SYNTHETIC assessed expected register",
        "obligations",
        {currency: total},
    )
    first = Decimal(total) - Decimal(tail)
    bank_rows = [
        {
            "id": "B1",
            "account": "BANK-1",
            "reference": "SYNTHETIC-POOLED-PAYMENT",
            "currency": currency,
            "date": "2026-06-28",
            "amount": str(-first),
        },
        {
            "id": "B2",
            "account": "BANK-1",
            "reference": "SYNTHETIC-BALANCE-PAYMENT",
            "currency": currency,
            "date": "2026-06-30",
            "amount": str(-Decimal(tail)),
        },
    ]
    bank = await source(
        c,
        h,
        eid,
        bank_rows,
        "SYNTHETIC independent retained bank movements",
        "transactions",
        {currency: "-" + total},
    )
    allocation_rows = []
    remaining = first
    for expected_row, record in zip(expected_rows, records, strict=True):
        amount = Decimal(expected_row["amount"])
        initial = min(remaining, amount)
        for bank_id, allocated in (("B1", initial), ("B2", amount - initial)):
            if allocated:
                allocation_rows.append(
                    {
                        "id": f"A{len(allocation_rows) + 1}",
                        "expected_id": expected_row["id"],
                        "reported_id": record[3],
                        "transaction_id": bank_id,
                        "currency": currency,
                        "amount": str(allocated),
                        "evidence_reference": "SYNTHETIC-BANK-ADVICE",
                        "rationale": "Independently assessed fictional pooled bank payment breakdown",
                    }
                )
        remaining -= initial
    allocations = await source(
        c,
        h,
        eid,
        allocation_rows,
        "SYNTHETIC retained bank allocation assessment",
        "obligation-allocations",
        {currency: total},
    )
    payload = {
        "workflow": "obligation-bank-allocations",
        "source_ids": {
            role: event["id"]
            for role, event in {
                "expected": expected,
                "reported": reported,
                "bank": bank,
                "allocations": allocations,
            }.items()
        },
        "account": "BANK-1",
        "currency": currency,
        "as_of": "2026-06-30",
        "settlement_start": "2026-06-01",
        "obligation_month_start": "2026-06",
        "obligation_month_end": "2026-06",
        "bank_payment_sign": "debit-negative",
        "title": "SYNTHETIC independently allocated obligation settlement",
        "rationale": "Reviewed reporting source, independent bank and explicit advice allocations",
    }
    await execute(c, h, eid, "country-workflow", payload, failed="Independently review all")
    for role, event in {
        "expected": expected,
        "reported": reported,
        "bank": bank,
        "allocations": allocations,
    }.items():
        assert (await decision(c, h, eid, event)).status_code == 403
        approved = await decision(c, reviewer[0], eid, event)
        assert approved.status_code == 201, approved.text
        payload["source_ids"][role] = approved.json()["id"]
    result = await execute(c, h, eid, "country-workflow", payload)
    controls = result["body"]["allocation_controls"]
    assert Decimal(controls["allocated_amount"]) == Decimal(total)
    assert (
        Decimal(controls["outstanding_expected"])
        == Decimal(controls["unallocated_bank_outflows"])
        == 0
    )
    obligation_rows = [row for row in result["body"]["rows"] if row["kind"] == "obligation"]
    assert sum(Decimal(row["late_settled_amount"]) for row in obligation_rows) == Decimal(tail)
    assert (await decision(c, h, eid, result)).status_code == 403
    assert (await decision(c, reviewer[0], eid, result)).status_code == 409
    for row in result["body"]["rows"]:
        if row["state"] != "MATCHED":
            disposition = await decision(c, h, eid, result, "accept", item_id=row["id"])
            assert disposition.status_code == 201, disposition.text
            result = disposition.json()
    approved = await decision(c, reviewer[0], eid, result)
    assert approved.status_code == 201, approved.text
    exported = await c.get(
        f"/api/v1/intelligence/engagements/{eid}/events/{approved.json()['id']}/export?format=xlsx",
        headers=h,
    )
    assert exported.status_code == 200, exported.text
    replacement = await c.post(
        base + "/evidence-files/" + document["id"],
        headers=h,
        files={"file": (filename, content.replace(b"SYNTHETIC", b"REVISED", 1), media)},
    )
    assert replacement.status_code == 201, replacement.text
    current = await c.get(
        f"/api/v1/intelligence/engagements/{eid}/events/{approved.json()['id']}", headers=h
    )
    assert current.status_code == 200 and current.json()["freshness"] == "STALE"
