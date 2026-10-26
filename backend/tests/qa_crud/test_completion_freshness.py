"""Source replacement must invalidate an otherwise approved engagement release."""

import os

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase2.test_pipeline import CSV, committed
from tests.phase4.test_workflows import (
    ACCEPTANCE,
    INDEPENDENCE,
    MATERIALITY,
    PAPER,
    action,
    actor,
    approve,
    create,
    grant,
    setup,
)
from tests.qa_crud.test_country_workflows import double_boundaries

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable database required"
)


async def prepare(
    c,
    h=None,
    options=None,
    eid=None,
    base=None,
    country="AE",
    quality=False,
    configured=False,
    actors=None,
):
    if h is None:
        h, options, eid, base = await setup(c)
    assert options is not None and eid is not None and base is not None
    if country == "IN" and not configured:
        entity = await c.post(
            "/api/v1/entities",
            headers=h,
            json=dict(
                client_id=options["client_id"],
                name="SYNTHETIC India completion controls",
                country="IN",
                jurisdiction="Synthetic India",
                functional_currency="INR",
                presentation_currency="INR",
            ),
        )
        assert entity.status_code == 201, entity.text
        period = await c.post(
            "/api/v1/financial-periods",
            headers=h,
            json=dict(
                entity_id=entity.json()["id"], start_date="2026-04-01", end_date="2027-03-31"
            ),
        )
        assert period.status_code == 201, period.text
        engagement = await c.post(
            "/api/v1/engagements",
            headers=h,
            json=dict(
                entity_id=entity.json()["id"],
                period_id=period.json()["id"],
                name="SYNTHETIC India source freshness audit",
                engagement_type="External Audit",
            ),
        )
        assert engagement.status_code == 201, engagement.text
        eid = engagement.json()["id"]
        base = f"/api/v1/engagements/{eid}/audit"
        options = dict(options, entity_id=entity.json()["id"], period_id=period.json()["id"])
    options = dict(options, currency="INR" if country == "IN" else "AED")
    partner = actors[0] if actors else await actor(h, "Audit Partner", "completion-partner")
    await grant(c, h, base, partner)
    quality_actor = (
        actors[1]
        if actors
        else (await actor(h, "Quality Reviewer", "completion-quality") if quality else None)
    )
    if quality_actor:
        await grant(c, h, base, quality_actor)
    response = await c.post(
        base + "/policy",
        headers=h,
        json=dict(review_chain=["Audit Partner"], quality_review_required=quality, methodology={}),
    )
    assert response.status_code == 200, response.text
    for person in [partner, *([quality_actor] if quality_actor else [])]:
        await approve(
            c, person[0], h, base, await create(c, person[0], base, "independence", INDEPENDENCE)
        )
    bodies = dict(
        acceptance=ACCEPTANCE,
        planning=dict(
            strategy="Synthetic strategy",
            scope="Synthetic complete engagement",
            timetable="Synthetic timing",
            methodology_version="Synthetic-v1",
            standards_edition="Explicit synthetic scope assessment",
        ),
        materiality=MATERIALITY,
        risks=dict(
            level="assertion",
            inherent_risk="high",
            control_risk="not_assessed",
            response="Synthetic source inspection",
            assertions=["occurrence"],
        ),
        programs=dict(methodology_version="Synthetic-v1", objective="Synthetic source procedures"),
        procedures=dict(
            methodology_version="Synthetic-v1",
            objective="Synthetic inspection",
            instructions="Inspect retained source",
            required_evidence="Synthetic source evidence",
        ),
    )
    for kind, body in bodies.items():
        await approve(c, h, partner[0], base, await create(c, h, base, kind, body))
    evidence = await create(
        c, h, base, "evidence", dict(category="Synthetic source support", retain_until="2036-12-31")
    )
    uploaded = await c.post(
        base + "/evidence-files/" + evidence["id"],
        headers=h,
        files={
            "file": (
                "SYNTHETIC-source.txt",
                b"Synthetic independent supporting document only",
                "text/plain",
            )
        },
    )
    assert uploaded.status_code == 201, uploaded.text
    evidence = (await c.get(base + "/records/" + evidence["id"], headers=h)).json()
    evidence = await approve(c, h, partner[0], base, evidence)
    content = CSV.replace(b"2026-01-01", b"2026-04-01") if country == "IN" else CSV
    batch, snapshot = await committed(c, h, options, content)
    sample = await c.post(
        "/api/v1/sampling/runs",
        headers=h,
        json=dict(snapshot_id=snapshot, method="random", size=2, seed=32),
    )
    assert sample.status_code == 201, sample.text
    selected = (await c.get("/api/v1/sampling/runs/" + sample.json()["id"], headers=h)).json()[
        "selection"
    ]["items"]
    testing = await approve(
        c,
        h,
        partner[0],
        base,
        await create(
            c,
            h,
            base,
            "testing",
            dict(
                sample_id=sample.json()["id"],
                population_completeness="Independent source row and debit/credit controls",
                reconciliation="Synthetic source snapshot",
                methodology_rationale="Human reviewed synthetic sample",
                conclusion="Synthetic source inspection complete",
                results=[
                    dict(
                        line_id=item["line_id"],
                        outcome="passed",
                        evidence_ids=[evidence["id"]],
                        observations="Synthetic source item inspected",
                    )
                    for item in selected
                ],
            ),
        ),
    )
    paper = await approve(
        c,
        h,
        partner[0],
        base,
        await create(
            c,
            h,
            base,
            "working-papers",
            dict(PAPER, sources=[dict(kind="record", id=testing["id"])]),
        ),
    )
    completion = await approve(
        c,
        h,
        partner[0],
        base,
        await create(
            c,
            h,
            base,
            "completion",
            dict(
                subsequent_events="Synthetic subsequent event assessment",
                going_concern="Synthetic going concern assessment",
                unadjusted_misstatements="Synthetic misstatement assessment",
                human_evidence_assessment="Synthetic independent sufficiency assessment",
                sources=[dict(kind="record", id=paper["id"])],
            ),
        ),
    )
    return dict(
        h=h,
        options=options,
        eid=eid,
        base=base,
        partner=partner,
        quality=quality_actor,
        batch=batch,
        snapshot=snapshot,
        content=content,
        testing=testing,
        paper=paper,
        completion=completion,
    )


async def move(c, fixture, target, expected=200):
    state = (await c.get(fixture["base"] + "/workspace", headers=fixture["h"])).json()["engagement"]
    response = await c.post(
        fixture["base"] + "/transition",
        headers=fixture["partner"][0],
        json=dict(
            version=state["version"],
            action=target,
            comments="Synthetic independently controlled lifecycle decision",
        ),
    )
    assert response.status_code == expected, response.text
    return response


async def replace_ledger(c, fixture):
    return await committed(
        c,
        fixture["h"],
        dict(fixture["options"], supersedes_id=fixture["batch"]),
        fixture["content"].replace(b"Adjustment", b"Revised synthetic source adjustment"),
    )


async def reassess(c, fixture, snapshot):
    from app.modules.audit_execution.schemas import BODIES

    sample = await c.post(
        "/api/v1/sampling/runs",
        headers=fixture["h"],
        json=dict(snapshot_id=snapshot, method="random", size=2, seed=32),
    )
    assert sample.status_code == 201, sample.text
    selected = (
        await c.get("/api/v1/sampling/runs/" + sample.json()["id"], headers=fixture["h"])
    ).json()["selection"]["items"]
    for kind, key in (
        ("testing", "testing"),
        ("working-papers", "paper"),
        ("completion", "completion"),
    ):
        obj = fixture[key]
        reopened = await action(c, fixture["partner"][0], fixture["base"], obj, "reopen")
        body = {
            name: value
            for name, value in reopened["body"].items()
            if name in BODIES[kind].model_fields
        }
        if kind == "testing":
            evidence = body["results"][0]["evidence_ids"]
            body.update(
                sample_id=sample.json()["id"],
                results=[
                    dict(
                        line_id=item["line_id"],
                        outcome="passed",
                        evidence_ids=evidence,
                        observations="New synthetic source item independently inspected",
                    )
                    for item in selected
                ],
            )
        patched = await c.patch(
            fixture["base"] + "/records/" + obj["id"],
            headers=fixture["h"],
            json=dict(
                version=reopened["version"],
                reference=obj["reference"],
                title=obj["title"],
                body=body,
            ),
        )
        assert patched.status_code == 200, patched.text
        fixture[key] = await approve(
            c, fixture["h"], fixture["partner"][0], fixture["base"], patched.json()
        )


@pytest.mark.parametrize("country", ["AE", "IN"])
@pytest.mark.parametrize(
    "stage,target", [("FIELDWORK", "REVIEW"), ("REVIEW", "REPORTING"), ("REPORTING", "COMPLETED")]
)
async def test_replaced_ledger_blocks_approved_engagement_completion(
    environment, monkeypatch, country, stage, target
):
    c = environment
    double_boundaries(monkeypatch)
    fixture = await prepare(c, country=country)
    initial = (await c.get(fixture["base"] + "/completion-checks", headers=fixture["h"])).json()
    assert initial["ready"], initial
    for intermediate in (
        "ACCEPTANCE_PENDING",
        "ACCEPTED",
        "PLANNING",
        "RISK_ASSESSMENT",
        "FIELDWORK",
        "REVIEW",
        "REPORTING",
    ):
        await move(c, fixture, intermediate)
        if intermediate == stage:
            break
    _, snapshot = await replace_ledger(c, fixture)
    stale = (await c.get(fixture["base"] + "/completion-checks", headers=fixture["h"])).json()
    assert not stale["ready"], stale
    source_check = next(
        check for check in stale["checks"] if check["code"] == "reviewed_source_freshness"
    )
    assert {item["record_id"] for item in source_check["source_issues"]} == {
        fixture[key]["id"] for key in ("testing", "paper", "completion")
    }
    assert all(item["freshness"] == "STALE" for item in source_check["source_issues"])
    assert (
        await c.get(fixture["base"] + "/records/" + fixture["paper"]["id"], headers=fixture["h"])
    ).json()["status"] == "APPROVED"
    await move(c, fixture, target, 409)
    await reassess(c, fixture, snapshot)
    refreshed = (await c.get(fixture["base"] + "/completion-checks", headers=fixture["h"])).json()
    assert refreshed["ready"], refreshed
    await move(c, fixture, target)


@pytest.mark.parametrize("country", ["AE", "IN"])
async def test_quality_decision_rechecks_sources_and_requires_reassessment(
    environment, monkeypatch, country
):
    c = environment
    double_boundaries(monkeypatch)
    fixture = await prepare(c, country=country, quality=True)
    for target in (
        "ACCEPTANCE_PENDING",
        "ACCEPTED",
        "PLANNING",
        "RISK_ASSESSMENT",
        "FIELDWORK",
        "REVIEW",
        "QUALITY_REVIEW",
    ):
        await move(c, fixture, target)
    state = (await c.get(fixture["base"] + "/workspace", headers=fixture["h"])).json()["engagement"]
    _, snapshot = await replace_ledger(c, fixture)
    payload = dict(
        version=state["version"],
        action="approve",
        comments="Synthetic independent engagement quality decision",
    )
    denied = await c.post(
        fixture["base"] + "/quality-review", headers=fixture["quality"][0], json=payload
    )
    assert denied.status_code == 409 and "Current reviewed sources" in denied.text, denied.text
    await reassess(c, fixture, snapshot)
    refreshed = (await c.get(fixture["base"] + "/completion-checks", headers=fixture["h"])).json()
    assert not refreshed["ready"]
    assert all(
        check["passed"] for check in refreshed["checks"] if check["code"] != "quality_review"
    )
    state = (await c.get(fixture["base"] + "/workspace", headers=fixture["h"])).json()["engagement"]
    payload["version"] = state["version"]
    allowed = await c.post(
        fixture["base"] + "/quality-review", headers=fixture["quality"][0], json=payload
    )
    assert allowed.status_code == 200, allowed.text
    assert (await c.get(fixture["base"] + "/completion-checks", headers=fixture["h"])).json()[
        "ready"
    ]
