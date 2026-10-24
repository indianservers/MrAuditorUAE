"""Synthetic source arithmetic and professional workflow controls; not legal-content certification."""

import os

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase2.test_pipeline import committed
from tests.phase4.test_workflows import actor, setup
from tests.unit.test_regulatory_evaluation import fixture

pytestmark = pytest.mark.skipif(os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable database")


async def test_india_reviewed_mapping_reporting_template_and_historical_sources(environment):
    c = environment
    h, options, eid, _ = await setup(c)
    reviewer = await actor(h, "Firm Administrator", "india-report-reviewer")
    cp = f"/api/v1/jurisdictions/engagements/{eid}/context"
    request = await c.post(
        cp,
        headers=h,
        json={
            "country": "IN",
            "framework": "Ind AS",
            "entity_type": "company",
            "as_of": "2026-12-31",
            "base_version": 0,
            "reason": "Synthetic independently assessed Indian reporting context",
        },
    )
    assert request.status_code == 201, request.text
    reviewed = await c.post(
        cp + "/decision",
        headers=reviewer[0],
        json={
            "request_id": request.json()["id"],
            "approve": True,
            "comments": "Synthetic independent assessment of framework and reporting jurisdiction",
        },
    )
    assert reviewed.status_code == 201, reviewed.text
    rule = fixture(
        country="IN",
        rule_key="IN-SYNTHETIC-DISCLOSURE",
        framework="Ind AS",
        applicability=[{"field": "nbfc", "operator": "equals", "values": ["true"]}],
        input_requirements=["nbfc"],
        validation_status="VALIDATED",
        professional_review_status="REVIEWED",
        last_reviewed="2026-10-24",
    ).model_dump(mode="json")
    rule["citations"][0].update(
        retrieval_status="RETRIEVED", document_sha256="b" * 64, retrieved_on="2026-10-24"
    )
    created = await c.post("/api/v1/regulatory/rules", headers=h, json=rule)
    assert created.status_code == 201, created.text
    rule_id = created.json()["id"]
    for action, who, sequence in [("approve", reviewer[0], 1), ("publish", h, 2)]:
        result = await c.post(
            f"/api/v1/regulatory/rules/{rule_id}/decisions",
            headers=who,
            json={
                "action": action,
                "expected_sequence": sequence,
                "comments": "Synthetic source validation attestation for workflow testing only",
            },
        )
        assert result.status_code == 201, result.text
    prefix = f"/api/v1/regulatory/engagements/{eid}"
    item = {
        "clause": "SYNTHETIC-NBFC-ONLY",
        "rule_id": rule_id,
        "state": "NOT_APPLICABLE",
        "facts": {"nbfc": False, "schedule_iii_division": "II"},
        "conclusion": "Synthetic NBFC-only disclosure is inapplicable to the non-NBFC fixture",
        "procedure": "Reviewed the synthetic entity applicability facts",
        "evidence_ids": [],
    }
    case = await c.post(
        prefix + "/checklists",
        headers=h,
        json={
            "area": "india-disclosures",
            "title": "SYNTHETIC Indian disclosure applicability",
            "items": [item],
            "rationale": "Synthetic explicitly documented Division II applicability review",
        },
    )
    assert case.status_code == 201, case.text
    case_review = await c.post(
        f"/api/v1/intelligence/engagements/{eid}/events/{case.json()['id']}/review",
        headers=reviewer[0],
        json={
            "expected_version": 1,
            "action": "approve",
            "comments": "Synthetic independent applicability and not-applicable conclusion review",
        },
    )
    assert case_review.status_code == 201, case_review.text
    _, snapshot = await committed(c, h, options)
    tb = (
        await c.get("/api/v1/accounting/trial-balance", headers=h, params={"snapshot_id": snapshot})
    ).json()["items"]
    assignments = {
        r["code"]: {
            "classification": {"100": "Assets", "300": "Equity", "500": "Expenses"}[r["code"]],
            "statement_group": "SYNTHETIC-" + r["code"],
        }
        for r in tb
    }
    mapping = await c.post(
        "/api/v1/accounting/mappings",
        headers=h,
        json={
            **{k: options[k] for k in ["client_id", "entity_id", "period_id"]},
            "name": "SYNTHETIC complete presentation mapping",
            "mapping": {"accounts": assignments},
            "approved": True,
        },
    )
    assert mapping.status_code == 201, mapping.text
    statement = await c.post(
        prefix + "/india-statements",
        headers=h,
        json={
            "snapshot_id": snapshot,
            "mapping_profile_id": mapping.json()["id"],
            "applicability_id": case_review.json()["id"],
            "division": "II",
            "rationale": "Synthetic actual source balances, reviewed mapping and assessed framework",
        },
    )
    assert statement.status_code == 201, statement.text
    output = statement.json()
    # Independent pencil calculation from CSV: cash 10.10 - 100.20; equity credit 10.10; expense 100.20.
    assert output["body"]["totals"]["Assets"] == "-90.10000000"
    assert output["body"]["period_profit"] == "-100.20000000"
    assert output["body"]["checks"]["statement_equation_balanced"]
    approved_statement = await c.post(
        f"/api/v1/intelligence/engagements/{eid}/events/{output['id']}/review",
        headers=reviewer[0],
        json={
            "expected_version": 1,
            "action": "approve",
            "comments": "Synthetic independent source arithmetic and presentation review",
        },
    )
    assert approved_statement.status_code == 201, approved_statement.text
    template = await c.post(
        prefix + "/report-templates",
        headers=h,
        json={
            "title": "SYNTHETIC source-reconciled Indian draft",
            "category": "schedule-iii",
            "blocks": [
                {
                    "key": "balances",
                    "title": "Source balances",
                    "kind": "financial_table",
                    "source_kind": "intelligence",
                    "source_id": approved_statement.json()["id"],
                }
            ],
            "rationale": "Synthetic report composition using exact reviewed source figures",
        },
    )
    assert template.status_code == 201, template.text
    generated_before_review = await c.post(
        prefix + "/reports",
        headers=h,
        json={
            "template_id": template.json()["id"],
            "rationale": "Synthetic unreviewed template must remain blocked",
        },
    )
    assert generated_before_review.status_code == 409
    template_review = await c.post(
        f"/api/v1/intelligence/engagements/{eid}/events/{template.json()['id']}/review",
        headers=reviewer[0],
        json={
            "expected_version": 1,
            "action": "approve",
            "comments": "Synthetic independent template and source-reference review",
        },
    )
    assert template_review.status_code == 201, template_review.text
    generated = await c.post(
        prefix + "/reports",
        headers=h,
        json={
            "template_id": template_review.json()["id"],
            "rationale": "Synthetic controlled generation from approved source versions",
        },
    )
    assert generated.status_code == 201, generated.text
    assert generated.json()["body"]["document_status"] == "DRAFT — NOT SIGNED OR FILED"
    for format in ["xlsx", "docx", "pdf"]:
        exported = await c.get(
            f"/api/v1/intelligence/engagements/{eid}/events/{generated.json()['id']}/export?format={format}",
            headers=h,
        )
        assert exported.status_code == 200 and len(exported.content) > 500, (
            format,
            exported.text[:100],
        )
