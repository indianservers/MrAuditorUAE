import os

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase5.test_reporting import prepared as ifrs_prepared
from tests.phase6.test_workflows import compute, release
from tests.phase6.test_workflows import prepared as tax_prepared

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable database required"
)


async def test_new_approved_note_invalidates_prior_ifrs_run(environment):
    c = environment
    h, eid, base, manager, partner, p, mapping, note, ready = await ifrs_prepared(c)
    run = (
        await c.post(f"/api/v1/ifrs/engagements/{eid}/financial-statements/{p['id']}", headers=h)
    ).json()
    await ready(
        "note",
        {
            "profile_id": p["id"],
            "note_reference": "NEW-NOTE",
            "text": "A newly approved material disclosure",
            "linked_line_codes": ["100"],
        },
    )
    result = await c.get(f"/api/v1/ifrs/engagements/{eid}/runs/{run['id']}", headers=h)
    assert result.status_code == 200, result.text
    assert not result.json()["dependencies_current"]


async def test_new_approved_tax_adjustment_invalidates_old_release(environment):
    c = environment
    h, eid, base, manager, partner, p, adj, note, rules, ready, financial = await tax_prepared(c)
    run = await compute(c, h, eid, p)
    await release(c, h, eid, base, manager, partner, run)
    await ready(
        "adjustment",
        {
            **{k: v for k, v in adj["body"].items() if not k.startswith("review_")},
            "accounting_amount": "200",
            "proposed_adjustment": "100",
        },
    )
    result = await c.get(f"/api/v1/tax/engagements/{eid}/runs/{run['id']}/export/json", headers=h)
    assert not result.json()["released"]
