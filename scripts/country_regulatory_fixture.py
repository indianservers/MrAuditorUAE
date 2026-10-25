"""Synthetic browser-only rates; never a production legal or exchange-rate pack."""

from tests.phase2.test_pipeline import CSV, committed
from tests.phase4.test_workflows import create, grant
from tests.qa_crud.test_country_workflows import decision, execute, source
from tests.qa_crud.regulatory_source_fixtures import retain
from tests.unit.test_regulatory_conversion import quote
from tests.unit.test_regulatory_evaluation import fixture


async def prepare(c, h, client_id, reviewer):
    from app.core.config import settings

    if settings().environment != "test" or not settings().database_url.endswith(
        "/auditos_country_workflows_test"
    ):
        raise RuntimeError(
            "Regulatory browser fixtures require the owned disposable database"
        )
    output = {}
    for country, currency, framework in (
        ("AE", "AED", "IFRS"),
        ("IN", "INR", "Ind AS"),
    ):
        start = "2026-04-01" if country == "IN" else "2026-01-01"
        end = "2027-03-31" if country == "IN" else "2026-12-31"
        entity = await c.post(
            "/api/v1/entities",
            headers=h,
            json={
                "client_id": client_id,
                "country": country,
                "name": f"SYNTHETIC {country} regulatory entity",
                "jurisdiction": "Synthetic browser verification",
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
                "start_date": start,
                "end_date": end,
            },
        )
        assert period.status_code == 201, period.text
        engagement = await c.post(
            "/api/v1/engagements",
            headers=h,
            json={
                "entity_id": entity.json()["id"],
                "period_id": period.json()["id"],
                "name": f"SYNTHETIC {country} regulatory conversion",
                "engagement_type": "External Audit",
            },
        )
        assert engagement.status_code == 201, engagement.text
        eid = engagement.json()["id"]
        base = f"/api/v1/engagements/{eid}/audit"
        await grant(c, h, base, reviewer)
        context_path = f"/api/v1/jurisdictions/engagements/{eid}/context"
        context = await c.post(
            context_path,
            headers=h,
            json={
                "country": country,
                "framework": framework,
                "entity_type": "company",
                "as_of": end,
                "base_version": 0,
                "reason": "Synthetic explicit reporting context for browser rate assessment",
            },
        )
        assert context.status_code == 201, context.text
        reviewed = await c.post(
            context_path + "/decision",
            headers=reviewer[0],
            json={
                "request_id": context.json()["id"],
                "approve": True,
                "comments": "Independent synthetic context verification",
            },
        )
        assert reviewed.status_code == 201, reviewed.text
        options = {
            "client_id": client_id,
            "entity_id": entity.json()["id"],
            "period_id": period.json()["id"],
            "currency": currency,
            "expected_rows": 4,
            "expected_debit": "110.30",
            "expected_credit": "110.30",
            "source_complete": True,
        }
        content = CSV.replace(b"2026-01-01", b"2026-04-01") if country == "IN" else CSV
        _, snapshot = await committed(c, h, options, content)
        accounts = (
            await c.get(
                "/api/v1/accounting/trial-balance",
                headers=h,
                params={"snapshot_id": snapshot},
            )
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
                "rationale": "Synthetic expense amount solely for browser conversion arithmetic",
            },
        )
        reviewed_lead = await decision(c, reviewer[0], eid, lead)
        assert reviewed_lead.status_code == 201, reviewed_lead.text
        evidence = await create(
            c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
        )
        uploaded = await c.post(
            base + "/evidence-files/" + evidence["id"],
            headers=h,
            files={
                "file": (
                    f"SYNTHETIC-{country}-rate.txt",
                    b"SYNTHETIC direct rate 4; no real market or legal rate",
                    "text/plain",
                )
            },
        )
        assert uploaded.status_code == 201, uploaded.text
        rate = quote(
            source_currency=currency,
            target_currency="USD",
            coverage_start=start,
            coverage_end=end,
            rate_date=end,
        )
        for key in ("source_evidence_version_id", "source_sha256"):
            rate.pop(key)
        rates = await source(
            c,
            h,
            eid,
            [rate],
            f"SYNTHETIC {country} retained direct rate",
            table_type="fx-rates",
            totals={},
            rule_document_version_id=uploaded.json()["id"],
        )
        reviewed_rates = await decision(c, reviewer[0], eid, rates)
        assert reviewed_rates.status_code == 201, reviewed_rates.text
        rule = fixture(
            country=country,
            rule_key=country + "-SYNTHETIC-FX-BROWSER",
            framework=framework,
            method="flat_rate",
            rate="0.125",
            calculation_currency="USD",
            effective_to="2027-12-31",
            input_requirements=["tax_base"],
            validation_status="VALIDATED",
            professional_review_status="REVIEWED",
            last_reviewed="2026-10-24",
        ).model_dump(mode="json")
        rule["citations"][0].update(
            retrieval_status="RETRIEVED",
            document_sha256="a" * 64,
            retrieved_on="2026-10-24",
        )
        retained_rule_source = await retain(c, h, rule)
        proposed = await c.post("/api/v1/regulatory/rules", headers=h, json=rule)
        assert proposed.status_code == 201, proposed.text
        for action, person, sequence in (
            ("approve", reviewer[0], 1),
            ("publish", h, 2),
        ):
            published = await c.post(
                f"/api/v1/regulatory/rules/{proposed.json()['id']}/decisions",
                headers=person,
                json={
                    "action": action,
                    "expected_sequence": sequence,
                    "comments": "Synthetic browser arithmetic rule; no legally adopted rate",
                },
            )
            assert published.status_code == 201, published.text
        output[country] = {
            "engagement": eid,
            "source": reviewed_lead.json()["id"],
            "rates": reviewed_rates.json()["id"],
            "rule": proposed.json()["id"],
            "source_currency": currency,
            "rule_reference_copy": retained_rule_source["id"],
        }
        if country == "AE":
            from tests.qa_crud.test_published_benefit_source import publish
            from tests.unit.test_practice_audit_workflows import benefit_employee, part_time_employee

            full, _, _ = await publish(c, h, reviewer[0], rule_key="AE-SYNTHETIC-FULL-BROWSER")
            from tests.unit.test_benefit_profiles import profile as benefit_profile
            from app.modules.regulatory.benefit_profiles import BenefitParameters
            from tests.unit.test_practice_audit_workflows import benefit_rule

            part_parameters = {key: value for key, value in benefit_rule(work_model="part-time").items() if key in BenefitParameters.model_fields}
            part = benefit_profile(rule_key="AE-SYNTHETIC-PART-BROWSER", benefit_parameters=part_parameters,
                validation_status="VALIDATED", professional_review_status="REVIEWED", last_reviewed="2026-10-24").model_dump(mode="json")
            await retain(c, h, part)
            part_created = await c.post("/api/v1/regulatory/rules", headers=h, json=part)
            assert part_created.status_code == 201, part_created.text
            for action, person, sequence in (("approve", reviewer[0], 1), ("publish", h, 2)):
                published = await c.post(f"/api/v1/regulatory/rules/{part_created.json()['id']}/decisions", headers=person,
                    json={"action": action, "expected_sequence": sequence,
                          "comments": "Synthetic part-time profile for browser control verification only"})
                assert published.status_code == 201, published.text
            employees = await source(c, h, eid, [benefit_employee(), part_time_employee(id="E2")],
                "SYNTHETIC published-profile employees", "benefit-employees", {"AED": "3150"})
            employee_review = await decision(c, reviewer[0], eid, employees)
            assert employee_review.status_code == 201, employee_review.text
            output[country]["benefits"] = {"employees": employee_review.json()["id"],
                "full_profile": full, "part_profile": part_created.json()["id"]}
        if country == "IN":
            from country_payroll_fixture import prepare as prepare_payroll

            output[country]["payroll"] = await prepare_payroll(c, h, eid, reviewer)
    return output
