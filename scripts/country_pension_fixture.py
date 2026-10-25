"""Synthetic contribution inputs for the owned disposable browser fixture only."""

from tests.phase4.test_workflows import create
from tests.qa_crud.test_country_workflows import decision, source
from tests.unit.test_pension_workflow import pension_fixture


async def prepare(c, h, eid, reviewer):
    from app.core.config import settings

    if settings().environment != "test" or not settings().database_url.endswith(
        "/auditos_country_workflows_test"
    ):
        raise RuntimeError(
            "Pension browser fixtures require the owned disposable database"
        )
    base = f"/api/v1/engagements/{eid}/audit"
    record = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    retained = await c.post(
        base + "/evidence-files/" + record["id"],
        headers=h,
        files={
            "file": (
                "SYNTHETIC-browser-pension-rule.pdf",
                b"%PDF-1.4\nSYNTHETIC CONTRIBUTION ARITHMETIC ONLY\n%%EOF",
                "application/pdf",
            )
        },
    )
    assert retained.status_code == 201, retained.text
    bases, rules, reported = pension_fixture()
    for rule in rules:
        rule.update(
            source_evidence_version_id=retained.json()["id"],
            source_sha256=retained.json()["sha256"],
        )
    output = {}
    for role, table, rows, totals in (
        ("bases", "pension-bases", bases, {"AED": "30000.03"}),
        ("rules", "pension-rules", rules, {}),
        ("reported", "pension-reported", reported, {"AED": "2500"}),
    ):
        item = await source(c, h, eid, rows, "SYNTHETIC pension " + role, table, totals)
        reviewed = await decision(c, reviewer[0], eid, item)
        assert reviewed.status_code == 201, reviewed.text
        output[role] = reviewed.json()["id"]
    return output


async def prepare_published(c, h, eid, reviewer):
    from app.core.config import settings
    from tests.qa_crud.test_published_pension_source import publish

    if settings().environment != "test" or not settings().database_url.endswith(
        "/auditos_country_workflows_test"
    ):
        raise RuntimeError(
            "Published pension browser fixtures require the owned disposable database"
        )
    bases, _, reported = pension_fixture()
    output = {"engagement": eid, "profiles": []}
    for component in ("EMPLOYEE", "EMPLOYER", "GOVERNMENT"):
        identifier, _ = await publish(c, h, reviewer[0], component)
        output["profiles"].append(identifier)
    for role, table, rows, totals in (
        ("bases", "pension-bases", bases, {"AED": "30000.03"}),
        ("reported", "pension-reported", reported, {"AED": "2500"}),
    ):
        item = await source(
            c, h, eid, rows, "SYNTHETIC published pension " + role, table, totals
        )
        reviewed = await decision(c, reviewer[0], eid, item)
        assert reviewed.status_code == 201, reviewed.text
        output[role] = reviewed.json()["id"]
    return output
