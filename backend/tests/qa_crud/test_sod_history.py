"""UAE first, then India: actual retained CSVs, independent review and frozen SoD."""

import hashlib
import json
import os
import uuid

import pytest
from sqlalchemy import select

from app.db.session import Session, tenant_context
from app.modules.audit_execution.models import EvidenceVersion
from app.modules.lineage.storage import ObjectStore
from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import action, actor, approve, create, grant, setup
from tests.qa_crud.test_country_workflows import double_boundaries
from tests.qa_crud.test_india_ecr_source import india_context

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable DB required"
)

CSV = b"principal,permission,scope,valid_from,valid_to\nSYN-user,create,A,2026-01-01,\nSYN-user,approve,B,2026-01-01,2026-06-30\n"


@pytest.mark.parametrize("country", ["AE", "IN"])
async def test_history_scope_sources_review_cache_and_monitoring(environment, monkeypatch, country):
    c = environment
    double_boundaries(monkeypatch)
    if country == "AE":
        h, _, eid, audit = await setup(c)
    else:
        h, eid, audit = await india_context(c)
    base = f"/api/v1/grc/engagements/{eid}"
    reviewer = await actor(h, "Firm Administrator", "sod-reviewer")
    owner = await actor(h, "Risk Owner", "sod-owner")
    for person in (reviewer, owner):
        await grant(c, h, audit, person)

    async def retained(name, content):
        paper = await create(
            c, h, audit, "evidence", dict(category="Other", retain_until="2036-12-31")
        )
        uploaded = await c.post(
            audit + "/evidence-files/" + paper["id"],
            headers=h,
            files={"file": (name, content, "text/csv" if name.endswith(".csv") else "text/plain")},
        )
        assert uploaded.status_code == 201, uploaded.text
        # Upload creates the next evidence record revision.
        paper["version"] += 1
        return await approve(c, h, reviewer[0], audit, paper)

    source = await retained("SYNTHETIC-access.csv", CSV)
    definition = await retained(
        "SYNTHETIC-policy.txt",
        b"Fictional effective policy 2026-01-01 to 2026-12-31. create/approve conflict. A overlaps B directly, appendix 2.\n",
    )
    controls = await retained(
        "SYNTHETIC-counts.txt",
        b"Fictional independently checked history: 2 assignments, 1 principal; 2026-01-01 to 2026-12-31.\n",
    )

    async def approved(kind, body):
        response = await c.post(
            base + "/records/" + kind,
            headers=h,
            json=dict(
                reference="SYN-" + str(uuid.uuid4())[:8], title="SYNTHETIC " + kind, body=body
            ),
        )
        assert response.status_code == 201, response.text
        return await approve(c, h, reviewer[0], base, response.json())

    common = dict(
        system="SYNTHETIC ERP",
        version_number=1,
        effective_from="2026-01-01",
        effective_to="2026-12-31",
        definition_evidence_id=definition["id"],
        pairs=[dict(first="create", second="approve", rationale="Independent authorization")],
    )
    exact = await approved("sod-rule", common)
    overlap = await approved(
        "sod-rule",
        dict(
            **common,
            scope_mode="reviewed-overlap",
            scope_overlaps=[
                dict(
                    first_scope="A",
                    second_scope="B",
                    rationale="Explicit fictional shared process scope",
                    evidence_reference="Appendix 2",
                )
            ],
        ),
    )

    async def imported(rule, historical=False, **changes):
        body = dict(
            system="SYNTHETIC ERP",
            rule_id=rule["id"],
            as_of="2026-12-31",
            source_evidence_id=source["id"],
        )
        if historical or rule["id"] == overlap["id"]:
            body.update(
                expected_assignment_count=2,
                expected_principal_count=1,
                population_control_evidence_id=controls["id"],
                population_control_reference="Independent counts memo 1",
            )
        if historical:
            body.update(
                period_start="2026-01-01",
                population_basis="validity-history",
                coverage_start="2026-01-01",
                coverage_end="2026-12-31",
                history_scope_assessment="Independent fictional scope and grant/revocation coverage assessment",
            )
        body.update(changes)
        return await c.post(
            base + "/sod/import",
            headers=h,
            data={
                "metadata": json.dumps(
                    dict(
                        reference="SYN-" + str(uuid.uuid4())[:8],
                        title="SYNTHETIC access",
                        body=body,
                    )
                )
            },
            files={"file": ("SYNTHETIC-access.csv", CSV, "text/csv")},
        )

    bad = await imported(overlap, True, expected_assignment_count=3)
    assert bad.status_code == 422
    bad = await imported(overlap, True, coverage_end="2026-06-30")
    assert bad.status_code == 422
    runs = []
    for rule, history, count in (
        (exact, False, 0),
        (exact, True, 0),
        (overlap, False, 0),
        (overlap, True, 1),
    ):
        response = await imported(rule, history)
        assert response.status_code == 201, response.text
        access = await approve(c, h, reviewer[0], base, response.json())
        response = await c.post(base + f"/records/{access['id']}/calculate", headers=h)
        assert response.status_code == 201, response.text
        run = response.json()
        runs.append(run)
        assert run["results"]["count"] == count
        assert run["results"]["source_binding_status"] == "CSV_BYTES_AND_ASSIGNMENTS_VERIFIED"
        assert len(run["dependencies"]) == (5 if history or rule["id"] == overlap["id"] else 4)
        repeated = await c.post(base + f"/records/{access['id']}/calculate", headers=h)
        assert repeated.status_code == 201 and repeated.json()["id"] == run["id"]
    assert runs[-1]["results"]["conflicts"][0]["scope_evidence_reference"] == "Appendix 2"
    assert runs[-1]["results"]["conflict_intervals"][0]["conflict_through"] == "2026-06-30"
    assert (
        runs[-1]["results"]["retained_source_receipts"][0]["sha256"]
        == hashlib.sha256(CSV).hexdigest()
    )
    assert (await c.get(base + "/runs", headers=owner[0])).status_code == 403

    # Monitoring reuses the same source binding and preserves all dependencies.
    monitor = await approved(
        "monitor-rule",
        dict(
            owner_id=reviewer[3],
            rule_key="SYN-access-history",
            version_number=1,
            input_kind="workpapers",
            rule_code="access_conflicts",
            criteria=dict(access_id=access["id"]),
            decision_rationale="Fictional permissions risk review",
        ),
    )
    from app.workers.accounting import process
    from app.workers.accounting import work as accounting_run

    monkeypatch.setattr(accounting_run, "apply_async", lambda **kwargs: None)
    response = await c.post(base + f"/monitoring/{monitor['id']}/execute", headers=h, json={})
    assert response.status_code == 202, response.text
    from app.core.security import decode_token

    user_id = str(decode_token(h["Authorization"].split()[1]))
    await process(response.json()["id"], h["X-Tenant-ID"], user_id)
    monitored = await c.get(base + "/runs?kind=monitoring", headers=h)
    # Inspect the immutable database snapshot too, avoiding assumptions about worker envelope names.
    from app.modules.grc.models import GRCRun

    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        executions = (
            await db.scalars(
                select(GRCRun).where(
                    GRCRun.engagement_id == uuid.UUID(eid), GRCRun.kind == "monitoring"
                )
            )
        ).all()
        assert executions, monitored.text
        assert executions[-1].results["matches"] == 1
        assert len(executions[-1].dependencies) == 6

    # A new implementation freezes a new immutable run instead of returning an old cache.
    from app.modules.grc import sod_sources

    with monkeypatch.context() as changed:
        changed.setattr(sod_sources, "implementation_hash", lambda: "b" * 64)
        refreshed = await c.post(base + f"/records/{access['id']}/calculate", headers=h)
        assert refreshed.status_code == 201, refreshed.text
        assert refreshed.json()["id"] != runs[-1]["id"]
        assert refreshed.json()["results"]["sod_implementation_sha256"] == "b" * 64

    # A manually edited workpaper cannot keep the CSV hash while altering assignments.
    response = await imported(overlap, True)
    draft = response.json()
    body = draft["body"]
    body["assignments"][0]["scope"] = "ALTERED"
    response = await c.patch(
        base + f"/records/{draft['id']}",
        headers=h,
        json=dict(
            version=draft["version"], reference=draft["reference"], title=draft["title"], body=body
        ),
    )
    assert response.status_code == 200, response.text
    submitted = await action(c, h, base, response.json(), "submit")
    await action(c, reviewer[0], base, submitted, "approve", expected=409)

    # Changing private object bytes without changing DB metadata must not reuse a cached run.
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        version = await db.scalar(
            select(EvidenceVersion).where(EvidenceVersion.record_id == uuid.UUID(source["id"]))
        )
        with ObjectStore().local(version.object_key, version.object_version) as path:
            original = path.read_bytes()
            try:
                path.write_bytes(b"tampered synthetic CSV")
                bad = await c.post(base + f"/records/{access['id']}/calculate", headers=h)
                assert bad.status_code == 409 and "integrity" in bad.text
            finally:
                path.write_bytes(original)
    # Reopening source evidence invalidates the approved dependent workpaper.
    await action(c, reviewer[0], audit, source, "reopen")
    stale = await c.post(base + f"/records/{access['id']}/calculate", headers=h)
    assert stale.status_code == 409
