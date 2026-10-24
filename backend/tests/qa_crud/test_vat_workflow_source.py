import os

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import action
from tests.phase7.test_vat_workflows import prepared
from tests.qa_crud.test_country_workflows import double_boundaries, execute

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable database required"
)


async def test_existing_vat_calculation_becomes_scoped_source_and_invalidates(
    environment, monkeypatch
):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base, manager, _, profile, invoices, *_ = await prepared(c)
    response = await c.post(
        f"/api/v1/vat/engagements/{eid}/computations/{profile['id']}", headers=h
    )
    assert response.status_code == 201, response.text
    run = response.json()
    path = f"/api/v1/intelligence/engagements/{eid}"
    choices = await c.get(path + "/vat-sources", headers=h)
    assert choices.status_code == 200, choices.text
    assert any(item["id"] == run["id"] for item in choices.json()["items"])
    source = await execute(
        c, h, eid, "workflow-vat", {"run_id": run["id"], "label": "Synthetic VAT engine bridge"}
    )
    assert source["kind"] == "workflow-source"
    assert source["body"]["table_type"] == "return-boxes"
    assert source["body"]["row_count"] == 14
    assert source["body"]["review_status"] == "UNVERIFIED"
    assert source["body"]["native_metadata"]["registration"] == profile["body"]["trn"]
    assert any(
        dep["type"] == "calculation" and dep["id"] == run["id"] for dep in source["dependencies"]
    )
    await action(c, manager[0], base, invoices[0], "reopen")
    choices = await c.get(path + "/vat-sources", headers=h)
    assert not any(item["id"] == run["id"] for item in choices.json()["items"])
    stale = await c.get(path + "/events/" + source["id"], headers=h)
    assert stale.status_code == 200, stale.text
    assert stale.json()["freshness"] != "current"
