"""Synthetic published India profile population for the owned browser campaign."""

from app.modules.regulatory.payroll_profiles import PayrollParameters
from tests.qa_crud.regulatory_source_fixtures import retain
from tests.qa_crud.test_country_workflows import decision, source
from tests.qa_crud.test_regulatory_sources import decide, propose
from tests.unit.test_payroll_profiles import profile
from tests.unit.test_payroll_rule_workflow import pf_fixture


async def prepare(c, h, eid, reviewer):
    from app.core.config import settings

    if settings().environment != "test" or not settings().database_url.endswith("/auditos_country_workflows_test"):
        raise RuntimeError("Payroll browser fixtures require the owned disposable database")
    bases, parameters, reported = pf_fixture()
    profiles = []
    for item in parameters:
        payload = profile().model_dump(mode="json")
        payload.update(rule_key="IN-SYNTHETIC-" + item["component"].replace(":", "-") + "-BROWSER",
            payroll_parameters=PayrollParameters.model_validate({key: value for key, value in item.items()
                if key in PayrollParameters.model_fields}).model_dump(mode="json"),
            validation_status="VALIDATED", professional_review_status="REVIEWED", last_reviewed="2026-10-24")
        payload["citations"][0]["url"] = "https://incometax.gov.in/"
        await retain(c, h, payload)
        identifier = await propose(c, h, payload)
        assert (await decide(c, reviewer[0], identifier)).status_code == 201
        published = await decide(c, h, identifier, action="publish", sequence=2)
        assert published.status_code == 201, published.text
        profiles.append(identifier)
    output = {"profiles": profiles}
    for role, kind, rows in (("bases", "payroll-bases", bases), ("reported", "obligations", reported)):
        imported = await source(c, h, eid, rows, "SYNTHETIC published payroll " + role, kind,
            {"INR": str(sum(int(row["amount"]) for row in rows))})
        approved = await decision(c, reviewer[0], eid, imported)
        assert approved.status_code == 201, approved.text
        output[role] = approved.json()["id"]
    return output
