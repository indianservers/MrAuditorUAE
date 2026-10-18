import os
from decimal import Decimal as D

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import action, create
from tests.phase6.test_workflows import compute, prepared, release, second_entity

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable database required"
)


async def test_loss_transfer_posts_once_and_survives_donor_recalculation(environment):
    c = environment
    h, eid, base, manager, partner, p, adj, note, rules, ready, financial = await prepared(c)
    loss = await ready(
        "loss",
        {
            "profile_id": p["id"],
            "origin_start": "2025-01-01",
            "origin_end": "2025-12-31",
            "amount": "2000000",
            "eligibility": "PASS",
            "ownership_continuity": True,
            "same_or_similar_business": True,
            "excluded_pre_ct_or_exempt": False,
            "source_reference": "Synthetic independently reviewed prior loss",
        },
    )
    await release(c, h, eid, base, manager, partner, await compute(c, h, eid, p))
    _, eid2, _, _, _, p2, *_ = await second_entity(c, h)
    transfer = await ready(
        "loss-transfer",
        {
            "profile_id": p["id"],
            "recipient_engagement_id": eid2,
            "recipient_profile_id": p2["id"],
            "loss_id": loss["id"],
            "amount": "500000",
            "common_ownership": "0.75",
            "own_loss_utilisation_review": "Donor's current approved utilization checked before transfer",
            "conditions": [
                {
                    "requirement": key,
                    "assessment": "PASS",
                    "rationale": "Synthetic statutory eligibility reviewed",
                    "evidence_record_ids": [note["id"]],
                }
                for key in [
                    "residence",
                    "alignment",
                    "not_exempt_or_qfzp",
                    "ownership_period",
                    "transfer_eligibility",
                ]
            ],
        },
    )
    path = f"/api/v1/tax/engagements/{eid}/loss-transfers/{transfer['id']}/post"
    posted = await c.post(path, headers=h)
    assert posted.status_code == 201, posted.text
    assert (await c.post(path, headers=h)).status_code == 409
    recipient = await compute(c, h, eid2, p2)
    assert D(recipient["results"]["loss_utilised"]) == 500000
    await release(c, h, eid, base, manager, partner, await compute(c, h, eid, p))
    ledger = (await c.get(f"/api/v1/tax/engagements/{eid}/loss-ledger/{p['id']}", headers=h)).json()
    assert D(ledger["items"][0]["available"]) == 300000


async def test_return_requires_current_release_checklist_and_external_evidence(environment):
    c = environment
    h, eid, base, manager, partner, p, adj, note, rules, ready, financial = await prepared(c)
    run = await compute(c, h, eid, p)
    await release(c, h, eid, base, manager, partner, run)
    body = {
        "tax_run_id": run["id"],
        "rationale": "Synthetic return reviewed",
        "filing_state": "READY_FOR_FILING",
        "checklist": [
            {
                "requirement": key,
                "assessment": "PASS",
                "rationale": "Synthetic checked",
                "evidence_record_ids": [note["id"]],
            }
            for key in [
                "taxpayer",
                "sources",
                "adjustments",
                "elections",
                "losses",
                "review_complete",
            ]
        ],
    }
    obj = await create(c, h, base, "tax-return", body)
    obj = await action(c, h, base, obj, "submit")
    obj = await action(c, manager[0], base, obj, "approve")
    obj = await action(c, partner[0], base, obj, "approve")
    assert obj["status"] == "APPROVED"
    body["filing_state"] = "FILED_EXTERNALLY"
    invalid = await c.post(
        base + "/tax-return",
        headers=h,
        json={"reference": "BAD-FILED", "title": "Missing filing proof", "body": body},
    )
    assert invalid.status_code == 422


async def test_foreign_tax_credit_and_exempt_income_never_double_relieve(environment):
    c = environment
    h, eid, base, manager, partner, p, adj, note, rules, ready, financial = await prepared(c)
    rule = await ready(
        "rule",
        {
            "rule_key": "foreign-credit",
            "rule_version": 1,
            "category": "exemption",
            "source_id": "CT-LAW",
            "article": "47",
            "decision_number": "Federal Decree-Law47",
            "effective_from": "2023-06-01",
            "known_from": "2023-06-01",
            "source_document_version": "Synthetic source review",
            "conditions": "Reviewed foreign taxable income and foreign tax",
            "exceptions": "No exempt-income credit or carryforward",
            "technical_review": "Synthetic independent review",
        },
    )
    await ready(
        "credit",
        {
            "profile_id": p["id"],
            "rule_id": rule["id"],
            "jurisdiction": "Synthetic jurisdiction",
            "foreign_taxable_income": "100000",
            "foreign_tax_paid": "12000",
            "uae_tax_attributable": "9000",
            "source_line_codes": ["400"],
            "evidence_record_ids": [note["id"]],
            "allocation_methodology": "Synthetic separate foreign taxable source allocation",
        },
    )
    result = await compute(c, h, eid, p)
    assert D(result["results"]["foreign_tax_credit"]) == 9000
    assert D(result["results"]["current_tax"]) == 101250
    exemption = {
        "profile_id": p["id"],
        "rule_id": rules["exemption"],
        "exemption_type": "domestic_dividend",
        "amount": "500000",
        "source_line_codes": ["400"],
        "conditions": [
            {
                "requirement": key,
                "assessment": "PASS",
                "rationale": "Synthetic reviewed dividend",
                "evidence_record_ids": [note["id"]],
            }
            for key in ["uae_resident_payer", "distribution_character"]
        ],
        "rationale": "Synthetic confirmed UAE domestic dividend",
    }
    await ready("exemption", exemption)
    assert (
        await c.post(f"/api/v1/tax/engagements/{eid}/computations/{p['id']}", headers=h)
    ).status_code == 422
    other = await ready(
        "profile", {k: v for k, v in p["body"].items() if not k.startswith("review_")}
    )
    await ready("exemption", {**exemption, "profile_id": other["id"]})
    result = await compute(c, h, eid, other)
    assert D(result["results"]["taxable_income"]) == 700000
    assert D(result["results"]["current_tax"]) == 29250


async def test_relief_transitional_and_foundation_are_explicit_assessments(environment):
    c = environment
    h, eid, base, manager, partner, p, adj, note, rules, ready, financial = await prepared(c)
    rule = await ready(
        "rule",
        {
            "rule_key": "restructuring",
            "rule_version": 1,
            "category": "exemption",
            "source_id": "CT-LAW",
            "article": "27",
            "decision_number": "Federal Decree-Law47",
            "effective_from": "2023-06-01",
            "known_from": "2023-06-01",
            "source_document_version": "Synthetic technical review",
            "conditions": "Reviewed statutory conditions",
            "exceptions": "Review all exceptions",
            "technical_review": "Synthetic independent legal technical review",
        },
    )
    conditions = [
        {
            "requirement": key,
            "assessment": "PASS",
            "rationale": "Synthetic reviewed evidence",
            "evidence_record_ids": [note["id"]],
        }
        for key in [
            "residence",
            "alignment",
            "not_exempt_or_qfzp",
            "commercial_reason",
            "statutory_transfer_conditions",
        ]
    ]
    obj = await ready(
        "restructuring",
        {
            "profile_id": p["id"],
            "rule_id": rule["id"],
            "relief_type": "business_restructuring",
            "transferor_entity_id": financial["results"].get(
                "entity_id", "00000000-0000-0000-0000-000000000001"
            ),
            "transferee_entity_id": "00000000-0000-0000-0000-000000000002",
            "transaction_date": "2026-02-28",
            "common_ownership": "0.8",
            "asset_or_business": "Synthetic business transfer",
            "consideration": "100000",
            "tax_value": "80000",
            "accounting_value": "100000",
            "election_made": True,
            "conditions": conditions,
            "clawback_event_date": "2027-01-01",
            "clawback_review": "Synthetic disposal within two years",
        },
    )
    result = await c.post(f"/api/v1/tax/engagements/{eid}/calculate/{obj['id']}", headers=h)
    assert result.status_code == 201, result.text
    assert result.json()["results"]["potential_clawback"]
    rule = await ready(
        "rule",
        {
            **{k: v for k, v in rule["body"].items() if not k.startswith("review_")},
            "rule_key": "transitional",
            "article": "61",
        },
    )
    obj = await ready(
        "transitional",
        {
            "profile_id": p["id"],
            "rule_id": rule["id"],
            "asset_category": "immovable_property",
            "acquisition_date": "2020-01-01",
            "first_tax_period_start": "2024-01-01",
            "election_evidence_id": note["id"],
            "accounting_value": "200000",
            "tax_value": "150000",
            "assessed_adjustment": "-50000",
            "valuation_evidence_id": note["id"],
            "methodology_and_conditions": "Manual independently reviewed allocation, no automatic uplift",
        },
    )
    result = await c.post(f"/api/v1/tax/engagements/{eid}/calculate/{obj['id']}", headers=h)
    assert (
        result.status_code == 201 and D(result.json()["results"]["assessed_adjustment"]) == -50000
    )
    obj = await ready(
        "foundation",
        {
            "profile_id": p["id"],
            "founders_beneficiaries": "Synthetic named family",
            "governance_evidence_id": note["id"],
            "holding_structure": "Synthetic asset holding",
            "conditions": conditions,
            "treatment": "APPLICATION_PENDING",
            "application_evidence_id": note["id"],
            "ongoing_compliance": "Annual professional assessment required",
        },
    )
    result = await c.post(f"/api/v1/tax/engagements/{eid}/calculate/{obj['id']}", headers=h)
    assert (
        result.status_code == 201 and result.json()["results"]["treatment"] == "APPLICATION_PENDING"
    )
    assert D((await compute(c, h, eid, p))["results"]["current_tax"]) == 110250
