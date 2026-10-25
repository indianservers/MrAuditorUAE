"""Synthetic rates only; real publication, retained ledger and independent review."""

import os
from decimal import Decimal

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase2.test_pipeline import CSV, committed
from tests.phase4.test_workflows import actor, create, grant, setup
from tests.qa_crud.regulatory_source_fixtures import retain
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.unit.test_regulatory_conversion import quote
from tests.unit.test_regulatory_evaluation import fixture

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable DB required"
)


@pytest.mark.parametrize("country,currency", [("AE", "AED"), ("IN", "INR"), ("AE", "USD")])
async def test_rate_assessment_binds_entity_currency_and_reviewed_tax_base(
    environment, monkeypatch, country, currency
):
    c = environment
    double_boundaries(monkeypatch)
    h, options, eid, base = await setup(c)
    if (country, currency) != ("AE", "AED"):
        entity = await c.post(
            "/api/v1/entities",
            headers=h,
            json={
                "client_id": options["client_id"],
                "name": "SYNTHETIC currency scope entity",
                "country": country,
                "jurisdiction": "Synthetic currency controls",
                "functional_currency": currency,
                "presentation_currency": currency,
            },
        )
        assert entity.status_code == 201, entity.text
        period = await c.post(
            "/api/v1/financial-periods",
            headers=h,
            json={
                "entity_id": entity.json()["id"],
                "start_date": "2026-04-01" if country == "IN" else "2026-01-01",
                "end_date": "2027-03-31" if country == "IN" else "2026-12-31",
            },
        )
        assert period.status_code == 201, period.text
        engagement = await c.post(
            "/api/v1/engagements",
            headers=h,
            json={
                "entity_id": entity.json()["id"],
                "period_id": period.json()["id"],
                "name": "SYNTHETIC rule currency review",
                "engagement_type": "External Audit",
            },
        )
        assert engagement.status_code == 201, engagement.text
        eid = engagement.json()["id"]
        base = f"/api/v1/engagements/{eid}/audit"
        options.update(entity_id=entity.json()["id"], period_id=period.json()["id"])
    options["currency"] = currency
    reviewer = await actor(h, "Firm Administrator", "regulatory-currency-reviewer")
    await grant(c, h, base, reviewer)
    framework = "IFRS" if country == "AE" else "Ind AS"
    context_path = f"/api/v1/jurisdictions/engagements/{eid}/context"
    context = await c.post(
        context_path,
        headers=h,
        json={
            "country": country,
            "framework": framework,
            "entity_type": "company",
            "as_of": "2026-12-31",
            "base_version": 0,
            "reason": "Synthetic explicitly assessed reporting context for currency controls",
        },
    )
    assert context.status_code == 201, context.text
    approval = await c.post(
        context_path + "/decision",
        headers=reviewer[0],
        json={
            "request_id": context.json()["id"],
            "approve": True,
            "comments": "Independently assessed synthetic country and reporting framework",
        },
    )
    assert approval.status_code == 201, approval.text
    content = CSV.replace(b"2026-01-01", b"2026-04-01") if country == "IN" else CSV
    _, snapshot = await committed(c, h, options, content)
    accounts = (
        await c.get("/api/v1/accounting/trial-balance", headers=h, params={"snapshot_id": snapshot})
    ).json()["items"]
    expense = next(row for row in accounts if row["code"] == "500")
    lead = await execute(
        c,
        h,
        eid,
        "lead",
        {
            "snapshot_id": snapshot,
            "account_ids": [expense["id"]],
            "section": "Administrative Expenses",
            "rationale": "Synthetic reviewed expense closing amount used only for arithmetic controls",
        },
    )
    reviewed = await decision(c, reviewer[0], eid, lead)
    assert reviewed.status_code == 201, reviewed.text

    async def publish(key, calculation_currency):
        payload = fixture(
            country=country,
            rule_key=country + "-" + key,
            framework=framework,
            method="flat_rate",
            rate="0.125",
            calculation_currency=calculation_currency,
            input_requirements=["tax_base"],
            effective_to="2027-12-31",
            validation_status="VALIDATED",
            professional_review_status="REVIEWED",
            last_reviewed="2026-10-24",
        ).model_dump(mode="json")
        payload["citations"][0].update(
            retrieval_status="RETRIEVED", document_sha256="a" * 64, retrieved_on="2026-10-24"
        )
        await retain(c, h, payload)
        created = await c.post("/api/v1/regulatory/rules", headers=h, json=payload)
        assert created.status_code == 201, created.text
        identifier = created.json()["id"]
        for action, person, sequence in [("approve", reviewer[0], 1), ("publish", h, 2)]:
            response = await c.post(
                f"/api/v1/regulatory/rules/{identifier}/decisions",
                headers=person,
                json={
                    "action": action,
                    "expected_sequence": sequence,
                    "comments": "Synthetic rate publication for currency isolation verification only",
                },
            )
            assert response.status_code == 201, response.text
        return identifier

    missing = fixture(
        country=country,
        rule_key=country + "-SYNTHETIC-NO-CURRENCY",
        framework=framework,
        method="flat_rate",
        rate="0.125",
        input_requirements=["tax_base"],
        validation_status="VALIDATED",
        professional_review_status="REVIEWED",
        last_reviewed="2026-10-24",
    ).model_dump(mode="json")
    missing["citations"][0].update(
        retrieval_status="RETRIEVED", document_sha256="a" * 64, retrieved_on="2026-10-24"
    )
    draft = await c.post("/api/v1/regulatory/rules", headers=h, json=missing)
    assert draft.status_code == 201, draft.text
    denied = await c.post(
        f"/api/v1/regulatory/rules/{draft.json()['id']}/decisions",
        headers=reviewer[0],
        json={
            "action": "approve",
            "expected_sequence": 1,
            "comments": "Synthetic attempt to approve a rate with unspecified currency",
        },
    )
    assert denied.status_code == 409 and "currency" in denied.text, denied.text

    rule = await publish("SYNTHETIC-CURRENCY", currency)
    path = f"/api/v1/regulatory/engagements/{eid}/assessments"
    request = {
        "rule_ids": [rule],
        "source_event_id": reviewed.json()["id"],
        "facts": {"tax_base": "100.20"},
        "rationale": "Synthetic rate applied to independently reviewed same-currency schedule; no legal tax amount claimed",
    }
    response = await c.post(path, headers=h, json=request)
    assert response.status_code == 201, response.text
    body = response.json()["body"]
    assert body["facts"]["functional_currency"] == currency
    assert body["rows"][0]["calculation"]["currency"] == currency
    assert Decimal(body["rows"][0]["calculation"]["unrounded_amount"]) == Decimal("12.525")
    wrong = "USD" if currency != "USD" else "AED"
    mismatch = await c.post(
        path,
        headers=h,
        json={**request, "facts": {"tax_base": "100.20", "functional_currency": wrong}},
    )
    assert mismatch.status_code == 422, mismatch.text
    duplicate = await c.post(path, headers=h, json={**request, "rule_ids": [rule, rule]})
    assert duplicate.status_code == 422, duplicate.text
    other = await publish("SYNTHETIC-OTHER-CURRENCY", wrong)
    mismatch = await c.post(path, headers=h, json={**request, "rule_ids": [other]})
    assert mismatch.status_code == 422 and "conversion workflow" in mismatch.text, mismatch.text
    evidence = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    uploaded = await c.post(
        base + "/evidence-files/" + evidence["id"],
        headers=h,
        files={
            "file": (
                "SYNTHETIC-rate-quote.txt",
                b"SYNTHETIC direct rate 4; arithmetic only",
                "text/plain",
            )
        },
    )
    assert uploaded.status_code == 201, uploaded.text
    q = quote(
        source_currency=currency,
        target_currency=wrong,
        source_evidence_version_id=uploaded.json()["id"],
        source_sha256=uploaded.json()["sha256"],
        coverage_start="2026-04-01" if country == "IN" else "2026-01-01",
        coverage_end="2027-03-31" if country == "IN" else "2026-12-31",
        rate_date="2027-03-31" if country == "IN" else "2026-12-31",
    )
    rates = await source(
        c,
        h,
        eid,
        [
            {
                key: value
                for key, value in q.items()
                if key not in {"source_evidence_version_id", "source_sha256"}
            }
        ],
        "SYNTHETIC independently assessed FX rate",
        table_type="fx-rates",
        totals={},
        rule_document_version_id=uploaded.json()["id"],
    )
    assert (await decision(c, h, eid, rates)).status_code == 403
    approved_rate = await decision(c, reviewer[0], eid, rates)
    assert approved_rate.status_code == 201, approved_rate.text
    conversion_request = {
        "source_event_id": reviewed.json()["id"],
        "rate_source_id": approved_rate.json()["id"],
        "rate_row_id": "SYN-FX",
        "decimal_places": 2,
        "rounding": "half-up",
        "target_amount": "400.80",
        "title": "SYNTHETIC reviewed source conversion",
        "assessment": "Synthetic retained direct rate and explicit rounding; no actual legal exchange rate claimed",
    }
    conversion_path = f"/api/v1/regulatory/engagements/{eid}/conversions"
    created = await c.post(conversion_path, headers=h, json=conversion_request)
    assert created.status_code == 201, created.text
    converted = created.json()
    assert converted["body"]["source_amount"] == reviewed.json()["body"]["totals"]["closing"]
    assert (await decision(c, h, eid, converted)).status_code == 403
    converted_request = {
        **request,
        "rule_ids": [other],
        "conversion_event_id": converted["id"],
        "facts": {"tax_base": "400.80"},
    }
    assert (await c.post(path, headers=h, json=converted_request)).status_code == 409
    approved_conversion = await decision(c, reviewer[0], eid, converted)
    assert approved_conversion.status_code == 201, approved_conversion.text
    converted_request["conversion_event_id"] = approved_conversion.json()["id"]
    assessed = await c.post(path, headers=h, json=converted_request)
    assert assessed.status_code == 201, assessed.text
    result = assessed.json()
    assert result["body"]["facts"]["functional_currency"] == currency
    assert result["body"]["facts"]["tax_base_currency"] == wrong
    assert result["body"]["rows"][0]["calculation"]["currency"] == wrong
    assert Decimal(result["body"]["rows"][0]["calculation"]["unrounded_amount"]) == Decimal("50.10")
    assert any(dep["id"] == approved_conversion.json()["id"] for dep in result["dependencies"])
    bad_control = await c.post(
        conversion_path, headers=h, json={**conversion_request, "target_amount": "400.79"}
    )
    assert bad_control.status_code == 422 and "control" in bad_control.text
    replacement = await c.post(
        base + "/evidence-files/" + evidence["id"],
        headers=h,
        files={
            "file": (
                "SYNTHETIC-rate-quote.txt",
                b"SYNTHETIC revised direct rate 5; arithmetic only",
                "text/plain",
            )
        },
    )
    assert replacement.status_code == 201, replacement.text
    for event in (approved_conversion.json(), result):
        detail = await c.get(
            f"/api/v1/intelligence/engagements/{eid}/events/{event['id']}", headers=h
        )
        assert detail.json()["freshness"] == "STALE"
