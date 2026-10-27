"""Real database audit workflows; all fixture records are explicitly synthetic."""

import os
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select, text

from app.core.security import access_token, hash_password
from app.db.models.platform import Membership, MembershipRole, Role, User
from app.db.session import Session, tenant_context
from tests.integration.test_platform import environment as environment
from tests.phase2.test_pipeline import committed, scope

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable migrated database required"
)


async def actor(headers, role, suffix):
    async with Session() as db, db.begin():
        await tenant_context(db, headers["X-Tenant-ID"])
        user = User(
            email=f"{suffix}@synthetic.example",
            password_hash=hash_password("synthetic-password-123"),
        )
        db.add(user)
        await db.flush()
        member = Membership(tenant_id=uuid.UUID(headers["X-Tenant-ID"]), user_id=user.id)
        db.add(member)
        await db.flush()
        r = await db.scalar(select(Role).where(Role.name == role))
        db.add(MembershipRole(membership_id=member.id, role_id=r.id))
        return (
            {**headers, "Authorization": "Bearer " + access_token(user.id)},
            str(member.id),
            str(r.id),
            str(user.id),
        )


async def setup(client):
    h, options = await scope(client)
    r = await client.post(
        "/api/v1/engagements",
        headers=h,
        json={
            "entity_id": options["entity_id"],
            "period_id": options["period_id"],
            "name": "SYNTHETIC Phase 4 statutory audit",
            "engagement_type": "External Audit",
        },
    )
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    return h, options, eid, f"/api/v1/engagements/{eid}/audit"


async def grant(client, h, base, actor_data):
    r = await client.post(
        base + "/team", headers=h, json={"membership_id": actor_data[1], "role_id": actor_data[2]}
    )
    assert r.status_code == 200, r.text


async def create(client, h, base, kind, body, reference=None):
    r = await client.post(
        base + "/" + kind,
        headers=h,
        json={
            "reference": reference or kind + "-" + str(uuid.uuid4())[:8],
            "title": "SYNTHETIC " + kind,
            "body": body,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


async def action(client, h, base, obj, value, expected=200):
    r = await client.post(
        base + "/records/" + obj["id"] + "/actions",
        headers=h,
        json={
            "version": obj["version"],
            "action": value,
            "comments": "Synthetic recorded professional decision for workflow test",
        },
    )
    assert r.status_code == expected, r.text
    return r.json()


async def approve(client, preparer, reviewer, base, obj):
    obj = await action(client, preparer, base, obj, "submit")
    return await action(client, reviewer, base, obj, "approve")


MATERIALITY = {
    "benchmark": "profit_before_tax",
    "benchmark_amount": "10000000",
    "selected_percentage": "5",
    "performance_percentage": "70",
    "trivial_percentage": "5",
    "benchmark_source": "Synthetic trial balance, PBT bridge",
    "rationale": "Selected by human for synthetic test only",
    "effective_date": "2026-10-18",
}
ACCEPTANCE = {
    k: "Synthetic documented response"
    for k in [
        "background",
        "ownership",
        "operations",
        "ethics",
        "conflicts",
        "management_integrity",
        "capability",
        "staffing",
        "previous_auditor",
        "scope_and_terms",
    ]
}
INDEPENDENCE = {
    "financial_interests": False,
    "relationships": False,
    "other_services": False,
    "threats": "None disclosed in synthetic test",
    "safeguards": "Partner assessment documented",
    "expires_on": str(date.today() + timedelta(days=365)),
}
PAPER = {
    "folder": "Planning",
    "sections": [{"heading": "Objective", "text": "Synthetic work performed"}],
    "conclusion": "Draft human conclusion for review",
}


async def test_materiality_self_approval_versions_and_lock(environment):
    c = environment
    h, _, _, base = await setup(c)
    staff = await actor(h, "Auditor", "staff")
    manager = await actor(h, "Audit Manager", "manager")
    partner = await actor(h, "Audit Partner", "partner")
    for a in [staff, manager, partner]:
        await grant(c, h, base, a)
    obj = await create(c, staff[0], base, "materiality", MATERIALITY)
    assert obj["body"]["calculation"]["overall"] == "500000.00"
    obj = await action(c, staff[0], base, obj, "submit")
    await action(c, staff[0], base, obj, "approve", 403)
    obj = await action(c, partner[0], base, obj, "approve")
    assert obj["status"] == "APPROVED"
    obj = await action(c, partner[0], base, obj, "lock")
    result = await c.patch(
        base + "/records/" + obj["id"],
        headers=staff[0],
        json={
            "version": obj["version"],
            "reference": obj["reference"],
            "title": obj["title"],
            "body": MATERIALITY,
        },
    )
    assert result.status_code == 409
    obj = await action(c, partner[0], base, obj, "reopen")
    result = await c.patch(
        base + "/records/" + obj["id"],
        headers=staff[0],
        json={
            "version": 1,
            "reference": obj["reference"],
            "title": obj["title"],
            "body": MATERIALITY,
        },
    )
    assert result.status_code == 409
    hist = await c.get(base + "/records/" + obj["id"] + "/history", headers=h)
    assert len(hist.json()["versions"]) == 5
    assert hist.json()["decisions"][-1]["decision"] == "reopen"


async def test_working_paper_review_chain_and_clearance(environment):
    c = environment
    h, _, _, base = await setup(c)
    staff = await actor(h, "Auditor", "staff")
    manager = await actor(h, "Audit Manager", "manager")
    partner = await actor(h, "Audit Partner", "partner")
    for a in [staff, manager, partner]:
        await grant(c, h, base, a)
    paper = await create(c, staff[0], base, "working-papers", PAPER, "WP-001")
    paper = await action(c, staff[0], base, paper, "submit")
    await action(c, partner[0], base, paper, "approve", 403)
    paper = await action(c, manager[0], base, paper, "return")
    patch = await c.patch(
        base + "/records/" + paper["id"],
        headers=staff[0],
        json={
            "version": paper["version"],
            "reference": "WP-001",
            "title": "Revised synthetic working paper",
            "body": {**PAPER, "conclusion": "Revised documented conclusion"},
        },
    )
    assert patch.status_code == 200, patch.text
    paper = await action(c, staff[0], base, patch.json(), "submit")
    paper = await action(c, manager[0], base, paper, "approve")
    assert paper["status"] == "REVIEW_REQUIRED"
    paper = await action(c, partner[0], base, paper, "approve")
    assert paper["status"] == "APPROVED"
    paper = await action(c, partner[0], base, paper, "lock")
    assert paper["status"] == "LOCKED"


async def test_role_revocation_unassigned_and_disabled(environment):
    c = environment
    h, _, eid, base = await setup(c)
    staff = await actor(h, "Auditor", "staff")
    assert (await c.get(base + "/workspace", headers=staff[0])).status_code == 403
    assert (await c.get("/api/v1/engagements", headers=staff[0])).json()["total"] == 0
    await grant(c, h, base, staff)
    assert (await c.get(base + "/workspace", headers=staff[0])).status_code == 200
    # Tenant policy revocation applies immediately without refreshing the access token.
    assert (
        await c.post(
            "/api/v1/admin/roles/" + staff[2] + "/permissions",
            headers=h,
            json={"permissions": ["audit.read", "engagements.read"]},
        )
    ).status_code == 200
    r = await c.post(
        base + "/working-papers",
        headers=staff[0],
        json={"reference": "X", "title": "Forbidden", "body": PAPER},
    )
    assert r.status_code == 403
    assert (
        await c.patch(
            "/api/v1/admin/users/" + staff[1],
            headers=h,
            json={"status": "disabled", "role_ids": [staff[2]]},
        )
    ).status_code == 200
    assert (await c.get(base + "/workspace", headers=staff[0])).status_code == 403
    assert (await c.get("/api/v1/engagements/" + eid, headers=staff[0])).status_code == 403


async def test_quality_reviewer_independence_and_trainee_finalize(environment):
    c = environment
    h, _, _, base = await setup(c)
    qr = await actor(h, "Quality Reviewer", "quality")
    trainee = await actor(h, "Audit Trainee", "trainee")
    await grant(c, h, base, qr)
    await grant(c, h, base, trainee)
    manager_role = next(
        r
        for r in (await c.get("/api/v1/admin/roles", headers=h)).json()["items"]
        if r["name"] == "Audit Manager"
    )
    assert (
        await c.post(
            base + "/team", headers=h, json={"membership_id": qr[1], "role_id": manager_role["id"]}
        )
    ).status_code == 409
    assert (
        await c.post(
            base + "/transition",
            headers=trainee[0],
            json={"version": 1, "action": "COMPLETED", "comments": "attempt"},
        )
    ).status_code == 403
    assert (
        await c.post(
            base + "/quality-review",
            headers=qr[0],
            json={"version": 1, "action": "approve", "comments": "attempt"},
        )
    ).status_code == 403


async def test_invalid_lifecycle_and_completion_gates(environment):
    c = environment
    h, _, eid, base = await setup(c)
    assert (
        await c.patch(
            "/api/v1/engagements/" + eid, headers=h, json={"version": 1, "status": "completed"}
        )
    ).status_code == 422
    assert (
        await c.post(
            base + "/transition",
            headers=h,
            json={"version": 1, "action": "COMPLETED", "comments": "attempt"},
        )
    ).status_code == 409
    r = await c.post(
        base + "/transition",
        headers=h,
        json={"version": 1, "action": "ACCEPTANCE_PENDING", "comments": "Begin acceptance"},
    )
    assert r.status_code == 200, r.text
    r = await c.post(
        base + "/transition",
        headers=h,
        json={"version": 2, "action": "ACCEPTED", "comments": "Missing approval"},
    )
    assert r.status_code == 409
    checks = (await c.get(base + "/completion-checks", headers=h)).json()
    assert not checks["ready"] and not any(
        x["passed"] for x in checks["checks"] if x["code"] in {"working-papers", "materiality"}
    )


async def test_evidence_versions_quarantine_hash_and_isolation(environment, monkeypatch, tmp_path):
    import hashlib

    from app.core.config import settings

    c = environment
    h, _, eid, base = await setup(c)
    monkeypatch.setattr(settings(), "source_storage_path", str(tmp_path))
    obj = await create(
        c, h, base, "evidence", {"category": "Invoice", "retain_until": "2036-12-31"}
    )
    content = b"invoice,amount\nSYNTHETIC,125.00\n"
    for n in [1, 2]:
        content = f"invoice,amount\nSYNTHETIC-v{n},125.00\n".encode()
        r = await c.post(
            base + "/evidence-files/" + obj["id"],
            headers=h,
            files={"file": ("synthetic.csv", content, "text/csv")},
        )
        assert r.status_code == 201, r.text
        assert r.json()["sha256"] == hashlib.sha256(content).hexdigest() and r.json()["number"] == n
        assert r.json()["scan_status"] == "QUARANTINED"
    duplicate = await c.post(
        base + "/evidence-files/" + obj["id"],
        headers=h,
        files={"file": ("synthetic.csv", content, "text/csv")},
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == r.json()["id"] and duplicate.json()["number"] == 2
    r = await c.get(
        base + "/evidence-files/" + obj["id"] + "/" + r.json()["id"] + "/download", headers=h
    )
    assert r.status_code == 409
    assert (
        await c.post(
            base + "/evidence-files/" + obj["id"],
            headers=h,
            files={"file": ("malicious.exe", b"MZbad", "application/octet-stream")},
        )
    ).status_code == 422
    viewer = await actor(h, "Client Viewer", "viewer")
    assert (
        await c.get(base + "/evidence-files/" + obj["id"], headers=viewer[0])
    ).status_code == 403


async def test_client_portal_request_response_and_internal_denial(
    environment, monkeypatch, tmp_path
):
    from app.core.config import settings

    c = environment
    h, options, _, base = await setup(c)
    monkeypatch.setattr(settings(), "source_storage_path", str(tmp_path))
    customer = await actor(h, "Client Accountant", "client")
    assert (
        await c.post(
            "/api/v1/admin/client-access",
            headers=h,
            json={"membership_id": customer[1], "client_id": options["client_id"]},
        )
    ).status_code == 200
    obj = await create(
        c,
        h,
        base,
        "requests",
        {
            "client_id": options["client_id"],
            "question": "Please upload the synthetic invoice",
            "narrative": "CONFIDENTIAL INTERNAL NOTE",
        },
    )
    assert (await c.get("/api/v1/client-portal/requests", headers=customer[0])).json()["total"] == 0
    obj = await action(c, h, base, obj, "SENT")
    rows = await c.get("/api/v1/client-portal/requests", headers=customer[0])
    assert (
        rows.json()["total"] == 1
        and "CONFIDENTIAL" not in rows.text
        and "body" not in rows.json()["items"][0]
    )
    viewed = await c.post(
        "/api/v1/client-portal/requests/" + obj["id"] + "/view", headers=customer[0]
    )
    assert viewed.json()["status"] == "VIEWED"
    up = await c.post(
        "/api/v1/client-portal/requests/" + obj["id"] + "/upload",
        headers=customer[0],
        files={"file": ("invoice.csv", b"id,amount\nSYNTHETIC,10\n", "text/csv")},
    )
    assert up.status_code == 201, up.text
    current = (await c.get("/api/v1/client-portal/requests", headers=customer[0])).json()["items"][
        0
    ]
    response = await c.post(
        "/api/v1/client-portal/requests/" + obj["id"] + "/responses",
        headers=customer[0],
        json={
            "version": current["version"],
            "response": "Synthetic invoice attached for your review",
        },
    )
    assert response.status_code == 200 and response.json()["status"] == "RESPONDED"
    for path in ["risks", "review-notes", "working-papers", "workspace"]:
        assert (await c.get(base + "/" + path, headers=customer[0])).status_code == 403
    outsider = await actor(h, "Client Accountant", "otherclient")
    assert (await c.get("/api/v1/client-portal/requests", headers=outsider[0])).json()["total"] == 0
    assert (
        await c.post("/api/v1/client-portal/requests/" + obj["id"] + "/view", headers=outsider[0])
    ).status_code == 404


async def test_anomaly_risk_ai_source_lineage(environment):
    c = environment
    h, options, _, base = await setup(c)
    _, snapshot = await committed(c, h, options)
    run = await c.post(
        "/api/v1/analytics/runs", headers=h, json={"snapshot_id": snapshot, "materiality": "50"}
    )
    assert run.status_code == 201, run.text
    finding = (
        await c.get("/api/v1/workspace/findings", headers=h, params={"run_id": run.json()["id"]})
    ).json()["items"][0]
    risk = await create(
        c,
        h,
        base,
        "risks",
        {
            "level": "assertion",
            "inherent_risk": "high",
            "control_risk": "not_assessed",
            "response": "Inspect original support for the synthetic flagged journal",
            "assertions": ["occurrence"],
            "sources": [{"kind": "finding", "id": finding["id"]}],
        },
    )
    r = await c.post(
        base + "/ai-actions",
        headers=h,
        json={
            "task": "financial_statement_risks",
            "sources": [{"kind": "record", "id": risk["id"]}],
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["body"]["output"]["citations"] == [risk["id"]]
    assert r.json()["status"] == "REVIEW_REQUIRED"
    assert r.json()["body"]["output"]["opinion_issued"] is False
    bad = await c.post(
        base + "/ai-actions",
        headers=h,
        json={"task": "risk_assertions", "sources": [{"kind": "record", "id": str(uuid.uuid4())}]},
    )
    assert bad.status_code == 422
    sample = await c.post(
        "/api/v1/sampling/runs",
        headers=h,
        json={"snapshot_id": snapshot, "method": "random", "size": 2, "seed": 42},
    )
    assert sample.status_code == 201, sample.text
    test = await create(
        c,
        h,
        base,
        "testing",
        {
            "sample_id": sample.json()["id"],
            "population_completeness": "Source counts reconciled",
            "reconciliation": "Synthetic committed snapshot",
            "methodology_rationale": "Human-selected size for workflow test; no assurance implied",
            "conclusion": "Synthetic testing draft",
            "sources": [{"kind": "sample", "id": sample.json()["id"]}],
        },
    )
    assert test["body"]["sample_id"] == sample.json()["id"]


@pytest.mark.parametrize("quality_required", [False, True])
async def test_complete_statutory_audit_human_workflow(
    environment, monkeypatch, tmp_path, quality_required
):
    from app.core.config import settings

    c = environment
    h, options, eid, base = await setup(c)
    staff = await actor(h, "Auditor", "fullstaff")
    partner = await actor(h, "Audit Partner", "fullpartner")
    for a in [staff, partner]:
        await grant(c, h, base, a)
    quality = await actor(h, "Quality Reviewer", "scenarioquality") if quality_required else None
    if quality:
        await grant(c, h, base, quality)
    assert (
        await c.post(
            base + "/policy",
            headers=h,
            json={
                "review_chain": ["Audit Partner"],
                "methodology": {},
                "quality_review_required": quality_required,
            },
        )
    ).status_code == 200

    async def move(target, headers=h):
        current = (await c.get(base + "/workspace", headers=h)).json()["engagement"]
        r = await c.post(
            base + "/transition",
            headers=headers,
            json={
                "version": current["version"],
                "action": target,
                "comments": "Synthetic scenario A human lifecycle decision",
            },
        )
        assert r.status_code == 200, r.text

    await move("ACCEPTANCE_PENDING")
    await approve(
        c, staff[0], partner[0], base, await create(c, staff[0], base, "acceptance", ACCEPTANCE)
    )
    await move("ACCEPTED", partner[0])
    await approve(
        c, staff[0], partner[0], base, await create(c, staff[0], base, "independence", INDEPENDENCE)
    )
    await approve(
        c, partner[0], h, base, await create(c, partner[0], base, "independence", INDEPENDENCE)
    )
    if quality:
        await approve(
            c, quality[0], h, base, await create(c, quality[0], base, "independence", INDEPENDENCE)
        )
    await move("PLANNING")
    await approve(
        c,
        staff[0],
        partner[0],
        base,
        await create(
            c,
            staff[0],
            base,
            "planning",
            {
                "strategy": "Synthetic audit strategy",
                "scope": "Synthetic external audit",
                "timetable": "Synthetic schedule",
                "methodology_version": "SYNTHETIC approved human profile",
                "standards_edition": "Synthetic standards applicability reference",
            },
        ),
    )
    await approve(
        c, staff[0], partner[0], base, await create(c, staff[0], base, "materiality", MATERIALITY)
    )
    await move("RISK_ASSESSMENT")
    risk = await approve(
        c,
        staff[0],
        partner[0],
        base,
        await create(
            c,
            staff[0],
            base,
            "risks",
            {
                "level": "assertion",
                "inherent_risk": "high",
                "control_risk": "not_assessed",
                "response": "Inspect original invoices",
                "assertions": ["occurrence"],
            },
        ),
    )
    await approve(
        c,
        staff[0],
        partner[0],
        base,
        await create(
            c,
            staff[0],
            base,
            "programs",
            {
                "methodology_version": "Synthetic-v1",
                "objective": "Inspect synthetic revenue support",
                "sources": [{"kind": "record", "id": risk["id"]}],
            },
        ),
    )
    procedure = await approve(
        c,
        staff[0],
        partner[0],
        base,
        await create(
            c,
            staff[0],
            base,
            "procedures",
            {
                "methodology_version": "Synthetic-v1",
                "objective": "Trace invoices",
                "instructions": "Inspect synthetic source invoice",
                "required_evidence": "Invoice",
                "owner_id": staff[3],
                "due_date": "2026-12-31",
                "sources": [{"kind": "record", "id": risk["id"]}],
            },
        ),
    )
    await move("FIELDWORK")
    # Scanner is a declared test double; production scanner remains an external integration.
    monkeypatch.setattr(settings(), "source_storage_path", str(tmp_path))
    monkeypatch.setattr("app.api.v1.audit_evidence.scan", lambda stream: "CLEAN")
    evidence = await create(
        c,
        staff[0],
        base,
        "evidence",
        {
            "category": "Synthetic invoice",
            "retain_until": "2036-12-31",
            "sources": [{"kind": "record", "id": procedure["id"]}],
        },
    )
    uploaded = await c.post(
        base + "/evidence-files/" + evidence["id"],
        headers=staff[0],
        files={"file": ("synthetic.csv", b"invoice,amount\nSYNTHETIC,100.20\n", "text/csv")},
    )
    assert uploaded.status_code == 201, uploaded.text
    downloaded = await c.get(
        base + "/evidence-files/" + evidence["id"] + "/" + uploaded.json()["id"] + "/download",
        headers=partner[0],
    )
    assert downloaded.status_code == 200 and downloaded.content.startswith(b"invoice")
    evidence = (await c.get(base + "/evidence", headers=h)).json()["items"][0]
    evidence = await approve(c, staff[0], partner[0], base, evidence)
    _, snapshot = await committed(c, h, options)
    sample = await c.post(
        "/api/v1/sampling/runs",
        headers=h,
        json={"snapshot_id": snapshot, "method": "random", "size": 2, "seed": 32},
    )
    assert sample.status_code == 201, sample.text
    await approve(
        c,
        staff[0],
        partner[0],
        base,
        await create(
            c,
            staff[0],
            base,
            "testing",
            {
                "sample_id": sample.json()["id"],
                "population_completeness": "Reconciled source row counts",
                "reconciliation": "Synthetic source snapshot",
                "methodology_rationale": "Human-selected sample, no assurance implied",
                "conclusion": "Human synthetic test conclusion",
                "results": [
                    {
                        "line_id": item["line_id"],
                        "outcome": "passed",
                        "evidence_ids": [evidence["id"]],
                        "observations": "Synthetic item traced to reviewed synthetic source attachment",
                    }
                    for item in (
                        await c.get("/api/v1/sampling/runs/" + sample.json()["id"], headers=h)
                    ).json()["selection"]["items"]
                ],
                "sources": [
                    {"kind": "record", "id": evidence["id"]},
                    {"kind": "sample", "id": sample.json()["id"]},
                ],
            },
        ),
    )
    paper = await create(
        c,
        staff[0],
        base,
        "working-papers",
        {
            **PAPER,
            "sources": [
                {"kind": "record", "id": evidence["id"]},
                {"kind": "record", "id": procedure["id"]},
            ],
        },
    )
    paper = await action(c, staff[0], base, paper, "submit")
    note = await create(
        c,
        partner[0],
        base,
        "review-notes",
        {
            "target_id": paper["id"],
            "assigned_reviewer": partner[3],
            "narrative": "Clarify the work performed",
        },
    )
    await action(c, partner[0], base, paper, "approve", 409)
    paper = await action(c, partner[0], base, paper, "return")
    revised = await c.patch(
        base + "/records/" + paper["id"],
        headers=staff[0],
        json={
            "version": paper["version"],
            "reference": paper["reference"],
            "title": paper["title"],
            "body": {**PAPER, "conclusion": "Revised human conclusion with clarified testing"},
        },
    )
    assert revised.status_code == 200, revised.text
    note = await action(c, staff[0], base, note, "resolve")
    note = await action(c, partner[0], base, note, "clear")
    paper = await approve(c, staff[0], partner[0], base, revised.json())
    await approve(
        c,
        h,
        partner[0],
        base,
        await create(
            c,
            h,
            base,
            "completion",
            {
                "subsequent_events": "Human documented subsequent-event work",
                "going_concern": "Human documented assessment",
                "unadjusted_misstatements": "Human documented evaluation",
                "human_evidence_assessment": "Human auditor documented sufficiency and reliability considerations; no opinion issued",
            },
        ),
    )
    controls = (await c.get(base + "/completion-checks", headers=h)).json()
    assert controls["ready"] == (not quality_required), controls
    await move("REVIEW")
    if quality:
        await move("QUALITY_REVIEW", partner[0])
        eng = (await c.get(base + "/workspace", headers=h)).json()["engagement"]
        payload = {
            "version": eng["version"],
            "action": "approve",
            "comments": "Synthetic independent engagement quality review decision",
        }
        qr = await c.post(base + "/quality-review", headers=quality[0], json=payload)
        assert qr.status_code == 200, qr.text
        assert (
            await c.post(base + "/quality-review", headers=quality[0], json=payload)
        ).status_code == 409
        assert (await c.get(base + "/completion-checks", headers=h)).json()["ready"]
    await move("REPORTING", partner[0])
    await move("COMPLETED", partner[0])
    assert (
        await c.post(
            base + "/working-papers",
            headers=staff[0],
            json={"reference": "late", "title": "Late change", "body": PAPER},
        )
    ).status_code == 409
    await move("ARCHIVED", partner[0])


async def test_methodology_versions_and_independent_approval(environment):
    c = environment
    h, _, _, base = await setup(c)
    other = await actor(h, "Firm Administrator", "methodologyreviewer")
    starter = (await c.get("/api/v1/admin/methodology/starter", headers=h)).json()
    assert len(starter["profile"]["procedures"]) == 20
    made = await c.post("/api/v1/admin/methodology", headers=h, json=starter)
    assert made.status_code == 201, made.text
    mid = made.json()["id"]
    assert (
        await c.post(
            "/api/v1/admin/methodology/" + mid + "/approve",
            headers=h,
            json={"rationale": "Self review"},
        )
    ).status_code == 403
    assert (
        await c.post(
            "/api/v1/admin/methodology/" + mid + "/approve",
            headers=other[0],
            json={"rationale": "Synthetic independent technical validation"},
        )
    ).status_code == 200
    result = await c.post(base + "/methodology/" + mid + "/instantiate", headers=h)
    assert result.status_code == 201 and len(result.json()["items"]) == 20, result.text
    assert (await c.post("/api/v1/admin/methodology", headers=h, json=starter)).status_code == 409


async def test_concurrent_edits_and_history_immutability(environment):
    import asyncio

    from sqlalchemy.exc import DBAPIError

    c = environment
    h, _, _, base = await setup(c)
    obj = await create(c, h, base, "working-papers", PAPER)
    data = {"version": 1, "reference": obj["reference"], "title": "Concurrent edit", "body": PAPER}
    results = await asyncio.gather(
        *[c.patch(base + "/records/" + obj["id"], headers=h, json=data) for _ in range(2)]
    )
    assert sorted(r.status_code for r in results) == [200, 409]
    async with Session() as db:
        await tenant_context(db, h["X-Tenant-ID"])
        with pytest.raises(DBAPIError):
            await db.execute(
                text("UPDATE audit_record_versions SET version=99 WHERE record_id=:rid"),
                {"rid": uuid.UUID(obj["id"])},
            )
        await db.rollback()


async def test_cross_tenant_audit_records_and_disabled_identity(environment):
    from app.db.models.platform import Tenant
    from app.modules.audit_execution.models import AuditRecord

    c = environment
    h, _, _, base = await setup(c)
    paper = await create(c, h, base, "working-papers", PAPER)
    async with Session() as db, db.begin():
        user = await db.scalar(select(User).where(User.email == "admin@example.com"))
        other = Tenant(name="SYNTHETIC other tenant")
        db.add(other)
        await db.flush()
        member = Membership(tenant_id=other.id, user_id=user.id)
        db.add(member)
        await db.flush()
        role = await db.scalar(select(Role).where(Role.name == "Firm Administrator"))
        db.add(MembershipRole(membership_id=member.id, role_id=role.id))
        otherid = str(other.id)
    otherheaders = {**h, "X-Tenant-ID": otherid}
    assert (await c.get(base + "/working-papers", headers=otherheaders)).status_code == 404
    assert (
        await c.get(base + "/records/" + paper["id"] + "/history", headers=otherheaders)
    ).status_code == 404
    async with Session() as db:
        await tenant_context(db, otherid)
        assert (
            await db.scalar(select(AuditRecord.id).where(AuditRecord.id == uuid.UUID(paper["id"])))
            is None
        )
    async with Session() as db, db.begin():
        user = await db.scalar(select(User).where(User.email == "admin@example.com"))
        user.status = "disabled"
    assert (await c.get(base + "/working-papers", headers=h)).status_code == 401


async def test_hallucinated_ai_citation_is_rejected(environment, monkeypatch):
    from app.modules.ai_engine.schemas import AIResponse
    from app.modules.audit_execution.ai_output import AuditAIOutput

    c = environment
    h, _, _, base = await setup(c)
    source = await create(c, h, base, "working-papers", PAPER)

    class HallucinatedProvider:
        async def generate(self, request):
            return AIResponse(
                output=AuditAIOutput(
                    summary="Synthetic invalid citation test",
                    observations=[],
                    proposed_procedures=[],
                    missing_information=[],
                    citations=[uuid.uuid4()],
                    requires_human_review=True,
                    evidence_sufficiency_determined=False,
                    opinion_issued=False,
                ),
                input_tokens=10,
                output_tokens=10,
                usage_source="mock_word_estimate",
            )

    monkeypatch.setattr("app.modules.ai_engine.service.MockProvider", HallucinatedProvider)
    result = await c.post(
        base + "/ai-actions",
        headers=h,
        json={
            "task": "working_paper_conclusions",
            "sources": [{"kind": "record", "id": source["id"]}],
        },
    )
    assert result.status_code == 201, result.text
    assert (
        result.json()["status"] == "failed"
        and result.json()["error_category"] == "invalid_citation"
    )
    assert (await c.get(base + "/ai", headers=h)).json()["total"] == 0


async def test_judgmental_sampling_requires_scoped_items_and_reason(environment):
    c = environment
    h, options, _, base = await setup(c)
    _, snapshot = await committed(c, h, options)
    population = await c.get(
        "/api/v1/workspace/ledger",
        headers=h,
        params={"entity_id": options["entity_id"], "period_id": options["period_id"]},
    )
    identifier = population.json()["items"][0]["id"]
    payload = {
        "snapshot_id": snapshot,
        "method": "judgmental",
        "selected_line_ids": [identifier],
        "selection_rationale": "Human selected an explicitly identified synthetic transaction",
    }
    result = await c.post(base + "/select-sample", headers=h, json=payload)
    assert result.status_code == 201, result.text
    items = (await c.get("/api/v1/sampling/runs/" + result.json()["id"], headers=h)).json()[
        "selection"
    ]["items"]
    assert [r["line_id"] for r in items] == [identifier]
    assert (
        await c.post(
            base + "/select-sample", headers=h, json={**payload, "selection_rationale": ""}
        )
    ).status_code == 422
    assert (
        await c.post(
            base + "/select-sample",
            headers=h,
            json={**payload, "selected_line_ids": [str(uuid.uuid4())]},
        )
    ).status_code == 422


async def test_ai_procedure_acceptance_requires_independent_human(environment, monkeypatch):
    import json

    from app.modules.ai_engine.schemas import AIResponse
    from app.modules.audit_execution.ai_output import AuditAIOutput

    c = environment
    h, _, _, base = await setup(c)
    reviewer = await actor(h, "Audit Partner", "aiprocedurereviewer")
    await grant(c, h, base, reviewer)
    source = await create(c, h, base, "working-papers", PAPER)

    class StructuredProposalTestDouble:
        async def generate(self, request):
            ids = json.loads(request.text)["evidence_ids"]
            return AIResponse(
                output=AuditAIOutput(
                    summary="SYNTHETIC proposal contract test",
                    observations=[],
                    proposed_procedures=[
                        "SYNTHETIC test procedure: inspect the supporting source record"
                    ],
                    missing_information=[],
                    citations=ids,
                    requires_human_review=True,
                    evidence_sufficiency_determined=False,
                    opinion_issued=False,
                ),
                input_tokens=10,
                output_tokens=10,
                usage_source="mock_word_estimate",
            )

    monkeypatch.setattr("app.modules.ai_engine.service.MockProvider", StructuredProposalTestDouble)
    result = await c.post(
        base + "/ai-actions",
        headers=h,
        json={"task": "audit_procedures", "sources": [{"kind": "record", "id": source["id"]}]},
    )
    assert result.status_code == 201, result.text
    proposal = result.json()
    payload = {
        "version": proposal["version"],
        "index": 0,
        "reference": "AI-P-001",
        "rationale": "Synthetic authorized human acceptance of test suggestion",
    }
    path = base + "/ai-actions/" + proposal["id"] + "/accept-procedure"
    assert (await c.post(path, headers=h, json=payload)).status_code == 403
    accepted = await c.post(path, headers=reviewer[0], json=payload)
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["status"] == "IN_PROGRESS"
    assert accepted.json()["body"]["sources"] == [{"kind": "record", "id": proposal["id"]}]
    assert (await c.post(path, headers=reviewer[0], json=payload)).status_code == 409


async def test_multiple_roles_differ_between_engagements_and_expire(environment):
    c = environment
    h, options, _, base = await setup(c)
    person = await actor(h, "Auditor", "multirole")
    await grant(c, h, base, person)
    roles = (await c.get("/api/v1/admin/roles", headers=h)).json()["items"]
    manager = next(r for r in roles if r["name"] == "Audit Manager")
    senior = next(r for r in roles if r["name"] == "Senior Auditor")
    assert (
        await c.post(
            base + "/team", headers=h, json={"membership_id": person[1], "role_id": manager["id"]}
        )
    ).status_code == 200
    another = await c.post(
        "/api/v1/engagements",
        headers=h,
        json={
            "entity_id": options["entity_id"],
            "period_id": options["period_id"],
            "name": "Synthetic second engagement",
            "engagement_type": "External Audit",
        },
    )
    second = "/api/v1/engagements/" + another.json()["id"] + "/audit"
    assert (
        await c.post(
            second + "/team", headers=h, json={"membership_id": person[1], "role_id": senior["id"]}
        )
    ).status_code == 200
    first = (await c.get(base + "/workspace", headers=person[0])).json()
    other = (await c.get(second + "/workspace", headers=person[0])).json()
    assert {"Auditor", "Audit Manager"} <= set(first["roles"])
    assert (
        "workingpaper.approve" in first["permissions"]
        and "workingpaper.approve" not in other["permissions"]
    )
    assert (
        await c.post(
            base + "/team",
            headers=h,
            json={
                "membership_id": person[1],
                "role_id": manager["id"],
                "expires_at": "2000-01-01T00:00:00Z",
            },
        )
    ).status_code == 200
    assert (
        "workingpaper.approve"
        not in (await c.get(base + "/workspace", headers=person[0])).json()["permissions"]
    )


async def test_finding_response_and_independent_resolution(environment):
    c = environment
    h, _, _, base = await setup(c)
    reviewer = await actor(h, "Audit Partner", "findingreviewer")
    await grant(c, h, base, reviewer)
    body = {
        "finding_type": "misstatement",
        "severity": "high",
        "financial_impact": "12500.00",
        "narrative": "Synthetic accounting difference awaiting management response",
    }
    finding = await create(c, h, base, "findings", body)
    await action(c, h, base, finding, "CLOSED", 409)
    finding = await action(c, h, base, finding, "UNDER_REVIEW")
    finding = await action(c, h, base, finding, "MANAGEMENT_RESPONSE_PENDING")
    updated = await c.patch(
        base + "/records/" + finding["id"],
        headers=h,
        json={
            "version": finding["version"],
            "reference": finding["reference"],
            "title": finding["title"],
            "body": {
                **body,
                "management_response": "Synthetic management adjustment and supporting source received",
            },
        },
    )
    assert updated.status_code == 200, updated.text
    finding = await action(c, h, base, updated.json(), "UNDER_REVIEW")
    await action(c, h, base, finding, "RESOLVED", 403)
    finding = await action(c, reviewer[0], base, finding, "RESOLVED")
    finding = await action(c, reviewer[0], base, finding, "CLOSED")
    assert finding["status"] == "CLOSED"
    history = (await c.get(base + "/records/" + finding["id"] + "/history", headers=h)).json()
    assert len(history["versions"]) == 7
