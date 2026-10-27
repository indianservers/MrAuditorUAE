import io
import os

import pytest
from openpyxl import load_workbook

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, grant, setup
from tests.qa_crud.test_country_workflows import (
    bank_payload,
    decision,
    double_boundaries,
    execute,
    source,
)
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.country_workflow_cases import transaction

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable database required"
)


async def prepare(c, h, eid, reviewer, country="AE", count=121):
    currency = "AED" if country == "AE" else "INR"
    events = {}
    for role, prefix in (("books", "L"), ("statement", "R")):
        rows = [
            transaction(
                id=f"{prefix}{i:03}",
                reference="SYNTHETIC-SHARED-REF",
                counterparty="SYNTHETIC شركة ألف"
                if country == "AE"
                else "SYNTHETIC भारत आपूर्तिकर्ता",
                currency=currency,
                amount="1",
                date="2026-06-01",
            )
            for i in range(count)
        ]
        event = await source(
            c,
            h,
            eid,
            rows,
            f"SYNTHETIC {country} {role} matching candidates",
            totals={currency: str(count)},
        )
        response = await decision(c, reviewer[0], eid, event)
        assert response.status_code == 201, response.text
        events[role] = response.json()
    return dict(
        events=events,
        payload=bank_payload(
            events["books"],
            events["statement"],
            currency=currency,
            book_closing=str(count),
            statement_closing=str(count),
            title=f"SYNTHETIC {country} complete competing bank candidates",
        ),
    )


@pytest.mark.parametrize("country", ["AE", "IN"])
async def test_complete_bank_candidate_pages_source_details_and_historical_export(
    environment, monkeypatch, country
):
    c = environment
    double_boundaries(monkeypatch)
    if country == "AE":
        h, _, eid, audit = await setup(c)
    else:
        h, eid, audit = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "candidate-source-reviewer")
    final = await actor(h, "Firm Administrator", "candidate-final-reviewer")
    for person in (reviewer, final):
        await grant(c, h, audit, person)
    fixture = await prepare(c, h, eid, reviewer, country)
    result = await execute(c, h, eid, "country-workflow", fixture["payload"])
    assert not result["body"]["blocked"]
    assert result["body"]["matching_contract"] == "indexed-transaction-candidates/1"
    assert result["body"]["ambiguity_link_count"] == 14641
    assert result["collection_totals"]["ambiguous"] == 121
    assert len(result["body"]["ambiguous"]) == 100
    assert len(result["body"]["ambiguous"][0]["candidate_ids"]) == 50
    assert result["body"]["ambiguous"][0]["candidate_count"] == 121
    assert result["body"]["ambiguous"][0]["candidate_preview_truncated"] is True
    prefix = f"/api/v1/intelligence/engagements/{eid}/events/{result['id']}"
    groups = await c.get(prefix + "?limit=1&ambiguity_offset=100&ambiguity_limit=100", headers=h)
    assert groups.status_code == 200
    assert len(groups.json()["body"]["ambiguous"]) == 21
    page = await c.get(prefix + "/bank-candidates?left_id=L120&offset=100&limit=100", headers=h)
    assert page.status_code == 200, page.text
    assert page.json()["total"] == 121 and len(page.json()["items"]) == 21
    assert page.json()["left"]["id"] == "L120" and page.json()["items"][-1]["id"] == "R120"
    assert page.json()["items"][-1]["reference"] == "SYNTHETIC-SHARED-REF"
    assert (await c.get(prefix + "/bank-candidates?left_id=unknown", headers=h)).status_code == 404
    assert (
        await c.get(prefix + "/bank-candidates?left_id=L120&limit=101", headers=h)
    ).status_code == 422
    outsider = await actor(h, "Audit Partner", "unassigned-candidate-reader")
    assert (
        await c.get(prefix + "/bank-candidates?left_id=L120", headers=outsider[0])
    ).status_code == 403
    assert (await decision(c, h, eid, result)).status_code == 403
    assert (await decision(c, final[0], eid, result)).status_code == 409
    for historical in (False, True):
        if historical:
            statement = fixture["events"]["statement"]["body"]["evidence_version_id"]
            import uuid

            from app.db.session import Session, tenant_context
            from app.modules.audit_execution.models import EvidenceVersion

            async with Session() as db:
                await tenant_context(db, h["X-Tenant-ID"])
                version = await db.get(EvidenceVersion, uuid.UUID(statement))
                record_id = str(version.record_id)
            changed = await c.post(
                audit + "/evidence-files/" + record_id,
                headers=h,
                files={
                    "file": (
                        "SYNTHETIC-replaced-statement.txt",
                        b"Synthetic replacement requires a new source review",
                        "text/plain",
                    )
                },
            )
            assert changed.status_code == 201, changed.text
            assert (await c.get(prefix, headers=h)).json()["freshness"] == "STALE"
            assert (
                await c.get(
                    prefix + "/bank-candidates?left_id=L120&offset=100&limit=100", headers=h
                )
            ).json()["items"][-1]["id"] == "R120"
        export = await c.get(prefix + "/export?format=xlsx", headers=h)
        assert export.status_code == 200
        workbook = load_workbook(io.BytesIO(export.content), read_only=True)
        candidates = list(workbook["Matching candidates"].values)
        assert len(candidates) == 14642
        assert candidates[-1][:4] == ("L120", "R120", "121", "COMPLETE_RETAINED_CANDIDATES")


async def test_excessive_competing_matches_fail_without_a_partial_result(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, audit = await setup(c)
    reviewer = await actor(h, "Firm Administrator", "candidate-bound-reviewer")
    await grant(c, h, audit, reviewer)
    fixture = await prepare(c, h, eid, reviewer, count=400)
    await execute(
        c, h, eid, "country-workflow", fixture["payload"], failed="candidate search bound exceeded"
    )
