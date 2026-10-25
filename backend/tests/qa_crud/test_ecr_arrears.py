"""Retained member text plus separate attributed context, reviewed arrears and staleness."""

import os

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_ecr_arrears import ARREARS, CONTEXT, options

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable database required"
)


async def retain(c, h, eid, base, context_headers=None):
    originals = []
    for label, content, headers in (
        ("arrears", ARREARS, h),
        ("context", CONTEXT, context_headers or h),
    ):
        record = await create(
            c, headers, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
        )
        uploaded = await c.post(
            base + "/evidence-files/" + record["id"],
            headers=headers,
            files={"file": ("SYNTHETIC-ecr-" + label + ".txt", content, "text/plain")},
        )
        assert uploaded.status_code == 201, uploaded.text
        originals.append((record, uploaded.json()))
    data = options(
        evidence_version_id=originals[0][1]["id"],
        arrear_context_evidence_version_id=originals[1][1]["id"],
    ).model_dump(mode="json")
    return data, originals


def obligations(role):
    return [
        dict(
            id=role + str(index),
            registration="SYNTHETIC-EPFO-001",
            subject=uan,
            period="2026-06",
            component=component,
            population="arrears",
            currency="INR",
            amount=amount,
            due_date="2026-07-31",
            payment_date="2026-07-20" if role == "payment" else None,
        )
        for index, (uan, component, amount) in enumerate(
            (
                ("100000000001", "PF:EMPLOYEE", "120"),
                ("100000000001", "PF:EPS", "83"),
                ("100000000001", "PF:EMPLOYER", "37"),
                ("100000000002", "PF:EMPLOYEE", "60"),
                ("100000000002", "PF:EPS", "0"),
                ("100000000002", "PF:EMPLOYER", "60"),
            ),
            1,
        )
    ]


async def test_retained_arrear_context_review_scope_comparison_export_and_replacement(
    environment, monkeypatch
):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base = await india_context(c)
    context_owner = await actor(h, "Firm Administrator", "arrear-context-owner")
    reviewer = await actor(h, "Firm Administrator", "arrear-independent-reviewer")
    for person in (context_owner, reviewer):
        await grant(c, h, base, person)
    data, originals = await retain(c, h, eid, base, context_owner[0])
    prepared = await execute(c, h, eid, "workflow-source", data)
    assert prepared["body"]["row_count"] == 6
    assert prepared["body"]["native_metadata"]["arrear_context_sha256"] == originals[1][1]["sha256"]
    assert {d["id"] for d in prepared["dependencies"] if d["type"] == "evidence"} == {
        item[1]["id"] for item in originals
    }
    assert (await decision(c, context_owner[0], eid, prepared)).status_code == 403
    assert (await decision(c, h, eid, prepared)).status_code == 403
    selected = {"return": prepared["id"]}
    for role in ("expected", "payment"):
        item = await source(
            c,
            h,
            eid,
            obligations(role),
            "Synthetic independent arrear " + role,
            "obligations",
            {"INR": "360"},
        )
        approved = await decision(c, reviewer[0], eid, item)
        assert approved.status_code == 201, approved.text
        selected[role] = approved.json()["id"]
    payload = dict(
        workflow="statutory-dues",
        source_ids=selected,
        as_of="2026-07-31",
        currency="INR",
        arrear_only=True,
        title="Synthetic arrear-only statutory comparison",
        rationale="Separate assessed arrear expectation, retained arrear return and independent contribution payment evidence",
    )
    await execute(
        c, h, eid, "country-workflow", payload, failed="review the arrear month attribution"
    )
    approved = await decision(c, reviewer[0], eid, prepared)
    assert approved.status_code == 201, approved.text
    payload["source_ids"]["return"] = approved.json()["id"]
    await execute(
        c,
        h,
        eid,
        "country-workflow",
        {**payload, "arrear_only": False},
        failed="arrear-only comparison scope",
    )
    regular = await source(
        c,
        h,
        eid,
        [{**row, "population": "regular"} for row in obligations("payment")],
        "Synthetic regular payment must not clear arrears",
        "obligations",
        {"INR": "360"},
    )
    await execute(
        c,
        h,
        eid,
        "country-workflow",
        {**payload, "source_ids": {**payload["source_ids"], "payment": regular["id"]}},
        failed="explicitly tagged as an arrear",
    )
    result = await execute(c, h, eid, "country-workflow", payload)
    assert result["body"]["exception_count"] == 0 and len(result["body"]["rows"]) == 6
    assert (
        result["body"]["obligation_population_scope"] == "ARREARS_ONLY_NOT_COMPLETE_MONTHLY_RETURN"
    )
    prefix = f"/api/v1/intelligence/engagements/{eid}"
    exported = await c.get(prefix + f"/events/{result['id']}/export?format=xlsx", headers=h)
    assert exported.status_code == 200 and exported.content[:2] == b"PK"
    for record, original in originals:
        downloaded = await c.get(
            base + f"/evidence-files/{record['id']}/{original['id']}/download", headers=h
        )
        assert downloaded.status_code == 200
    changed = await c.post(
        base + "/evidence-files/" + originals[1][0]["id"],
        headers=context_owner[0],
        files={
            "file": (
                "SYNTHETIC-context-replacement.txt",
                CONTEXT + b" Updated source assessment.",
                "text/plain",
            )
        },
    )
    assert changed.status_code == 201
    for identifier in (prepared["id"], result["id"]):
        history = await c.get(prefix + "/events/" + identifier, headers=h)
        assert history.status_code == 200 and history.json()["freshness"] == "STALE"
    await execute(c, h, eid, "workflow-source", data, failed="document was superseded")


async def test_arrear_profile_is_not_available_to_uae(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    data, _ = await retain(c, h, eid, base)
    await execute(c, h, eid, "workflow-source", data, failed="requires an India engagement")
