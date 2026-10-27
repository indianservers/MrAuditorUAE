"""Synthetic source-linked MD84 nonresident audit revenue; no client qualification."""

import os
from copy import deepcopy

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import action, actor, create, grant
from tests.phase6.test_workflows import compute, prepared

pytestmark = pytest.mark.skipif(os.getenv("INTEGRATION_TESTS") != "1", reason="Dedicated test DB")


@pytest.mark.parametrize(
    "amount,complete,required",
    [
        ("0", True, False),
        ("50000000", True, False),
        ("50000000.00000001", True, True),
        ("0", False, None),
    ],
)
async def test_nonresident_revenue_is_reviewed_bound_and_current(
    environment, amount, complete, required
):
    c = environment
    h, eid, base, manager, partner, original, adj, note, rules, ready, financial = await prepared(
        c, scale=2000000
    )
    audit_manager = await actor(h, "Audit Manager", "nr-revenue-manager")
    audit_partner = await actor(h, "Audit Partner", "nr-revenue-partner")
    await grant(c, h, base, audit_manager)
    await grant(c, h, base, audit_partner)
    facts = dict(
        amount=amount,
        currency="AED",
        period_start="2026-01-01",
        period_end="2026-12-31",
        scope="uae_pe_and_nexus",
        population_complete=complete,
        assessment="SYNTHETIC independently assessed UAE PE/nexus revenue population",
    )
    paper = await create(
        c,
        h,
        base,
        "working-papers",
        dict(
            folder="SYNTHETIC nonresident audit scope",
            sections=[
                dict(
                    heading="Revenue population",
                    text="Synthetic assessment only, not an independently qualified client case",
                )
            ],
            financial_tables=[dict(title="SYNTHETIC UAE PE/nexus revenue", values=facts)],
            conclusion="Synthetic source-scope controls for MD84 audit-documentation threshold only",
        ),
    )
    body = {k: v for k, v in original["body"].items() if not k.startswith("review_")}
    body.update(
        classification="nonresident_juridical",
        resident=False,
        nonresident_audit_revenue=facts
        | dict(evidence_id=paper["id"], source_path=["financial_tables", 0, "values"]),
    )

    async def propose(candidate):
        return await c.post(
            base + "/tax-profile",
            headers=h,
            json=dict(
                reference="SYNTHETIC NR audit scope",
                title="SYNTHETIC NR audit profile",
                body=candidate,
            ),
        )

    assert (await propose(body)).status_code == 409
    paper = await action(c, h, base, paper, "submit")
    paper = await action(c, audit_manager[0], base, paper, "approve")
    paper = await action(c, audit_partner[0], base, paper, "approve")
    wrong = deepcopy(body)
    wrong["nonresident_audit_revenue"]["amount"] = "1" if amount == "0" else "0"
    assert (await propose(wrong)).status_code == 422
    unrelated = deepcopy(body)
    unrelated["nonresident_audit_revenue"]["evidence_id"] = note["id"]
    assert (await propose(unrelated)).status_code == 422
    wrong = deepcopy(body)
    wrong["nonresident_audit_revenue"]["period_start"] = "2026-02-01"
    assert (await propose(wrong)).status_code == 422
    profile = await ready("profile", body)
    result = await compute(c, h, eid, profile)
    assessed = result["results"]["audit_statement_obligation"]
    assert assessed["required_for_ct"] is required
    assert assessed["threshold_revenue"] == (amount if complete else None)
    assert result["results"]["validation"]["ready"] is (required is False)
    assert any(d["id"] == paper["id"] for d in result["dependencies"])
    endpoint = f"/api/v1/tax/engagements/{eid}/runs/{result['id']}"
    assert (await c.get(endpoint, headers=h)).json()["dependencies_current"]
    saved = deepcopy(result["results"])
    await action(c, audit_partner[0], base, paper, "reopen")
    historical = await c.get(endpoint, headers=h)
    assert not historical.json()["dependencies_current"] and historical.json()["results"] == saved
    assert (
        await c.post(f"/api/v1/tax/engagements/{eid}/computations/{profile['id']}", headers=h)
    ).status_code == 409
