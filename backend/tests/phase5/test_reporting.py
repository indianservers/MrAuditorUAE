"""Synthetic end-to-end reporting against PostgreSQL RLS and actual import services."""

import os
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase2.test_pipeline import committed
from tests.phase4.test_workflows import action, actor, approve, create, grant, setup
from tests.phase5.test_calculations import ECL_INPUT, LEASE

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable database required"
)
CSV = b"Account Code,Account Name,Journal Number,Posting Date,Debit,Credit,Source ID,Opening,Manual,Narration\n100,Cash,OPEN,2026-01-01,100,0,L1,true,false,Opening\n300,Equity,OPEN,2026-01-01,0,100,L2,true,false,Opening\n100,Cash,S1,2026-06-01,50,0,L3,false,false,Sale\n400,Revenue,S1,2026-06-01,0,50,L4,false,false,Sale\n500,Expense,E1,2026-06-01,20,0,L5,false,false,Expense\n100,Cash,E1,2026-06-01,0,20,L6,false,false,Expense\n"


async def prepared(c, scope_data=None, suffix="", scale=1):
    h, opts, eid, base = scope_data or await setup(c)
    reviewer = await actor(h, "Audit Manager", "ifrs-reviewer" + suffix)
    partner = await actor(h, "Audit Partner", "ifrs-partner" + suffix)
    await grant(c, h, base, reviewer)
    await grant(c, h, base, partner)
    import csv
    import io

    rows = list(csv.reader(io.StringIO(CSV.decode())))
    for row in rows[1:]:
        row[4] = str(Decimal(row[4]) * scale)
        row[5] = str(Decimal(row[5]) * scale)
    stream = io.StringIO()
    csv.writer(stream, lineterminator="\n").writerows(rows)
    opts.update(expected_rows=6, expected_debit=str(170 * scale), expected_credit=str(170 * scale))
    _, sid = await committed(c, h, opts, stream.getvalue().encode())

    async def ready(kind, body):
        obj = await create(c, h, base, "ifrs-" + kind, body)
        return await approve(c, h, reviewer[0], base, obj)

    p = await ready(
        "profile",
        {
            "snapshot_id": sid,
            "presentation_currency": "AED",
            "technical_validation": "Synthetic corporate reporting basis verified by test reviewer",
        },
    )
    entries = []
    for code, label, section in [
        ("100", "Cash", "assets"),
        ("300", "Capital", "equity"),
        ("400", "Revenue", "income"),
        ("500", "Expense", "expenses"),
    ]:
        entries.append(
            {
                "account_code": code,
                "allocations": [
                    {
                        "line_code": code,
                        "label": label,
                        "section": section,
                        "note": "N1",
                        "is_cash": code == "100",
                    }
                ],
            }
        )
    mapping = await ready(
        "mapping",
        {
            "profile_id": p["id"],
            "accounts": entries,
            "rationale": "Synthetic independently classified chart",
        },
    )
    await ready(
        "cash-flow",
        {
            "profile_id": p["id"],
            "method": "indirect",
            "policy": "Synthetic interest policy",
            "movement_schedule_source": "Imported ledger, no noncash movements",
        },
    )
    note = await ready(
        "note",
        {
            "profile_id": p["id"],
            "note_reference": "N1",
            "text": "Synthetic disclosure for testing only. Basis and judgments independently reviewed.",
            "linked_line_codes": ["100", "300", "400", "500"],
        },
    )
    for category in [
        "presentation",
        "policies",
        "judgments",
        "events_after_reporting",
        "going_concern",
        "N1",
    ]:
        await ready(
            "disclosure",
            {
                "profile_id": p["id"],
                "standard": "IAS 1",
                "category": category,
                "applicability": "applicable",
                "rationale": "Synthetic human assessment",
                "note_id": note["id"],
            },
        )
    return h, eid, base, reviewer, partner, p, mapping, note, ready


async def test_company_statements_approval_and_exports(environment, tmp_path):
    c = environment
    h, eid, base, reviewer, partner, p, mapping, note, ready = await prepared(c)
    api = f"/api/v1/ifrs/engagements/{eid}"
    response = await c.post(api + "/financial-statements/" + p["id"], headers=h)
    assert response.status_code == 201, response.text
    run = response.json()
    data = run["results"]
    assert data["validation"]["ready"], data["validation"]
    assert Decimal(data["totals"]["assets"]) == 130
    assert Decimal(data["totals"]["equity"]) == 130
    assert Decimal(data["totals"]["profit"]) == 30
    assert Decimal(data["cash_flow"]["difference"]) == 0
    assert Decimal(data["changes_in_equity"]["closing"]) == 130
    package = await create(
        c,
        h,
        base,
        "ifrs-financials",
        {"run_id": run["id"], "release_rationale": "Synthetic package reconciled and reviewed"},
    )
    package = await action(c, h, base, package, "submit")
    await action(c, h, base, package, "approve", 403)
    package = await action(c, reviewer[0], base, package, "approve")
    assert package["status"] != "APPROVED"
    package = await action(c, partner[0], base, package, "approve")
    assert package["status"] == "APPROVED"
    for format, signature in [("json", b"{"), ("pdf", b"%PDF"), ("xlsx", b"PK"), ("docx", b"PK")]:
        response = await c.get(api + f"/runs/{run['id']}/export/{format}", headers=h)
        assert response.status_code == 200, response.text
        assert response.content.startswith(signature)
        (tmp_path / f"synthetic-financials.{format}").write_bytes(response.content)
        if os.getenv("PHASE5_ARTIFACT_DIR"):
            dest = Path(os.environ["PHASE5_ARTIFACT_DIR"])
            dest.mkdir(parents=True, exist_ok=True)
            (dest / f"synthetic-financials.{format}").write_bytes(response.content)
    # Reopening a material input prevents release and labels future exports as drafts.
    await action(c, reviewer[0], base, mapping, "reopen")
    validation = (await c.get(api + f"/runs/{run['id']}/validate", headers=h)).json()
    assert not validation["dependencies_current"]
    output = (await c.get(api + f"/runs/{run['id']}/export/json", headers=h)).json()
    assert not output["released"]


@pytest.mark.parametrize(
    "kind,body,key,expected",
    [("lease", LEASE, "initial_liability", "1000"), ("ecl", ECL_INPUT, "total_ecl", None)],
)
async def test_approved_calculation_and_balanced_overlay(environment, kind, body, key, expected):
    c = environment
    h, eid, base, reviewer, partner, p, mapping, note, ready = await prepared(c)
    api = f"/api/v1/ifrs/engagements/{eid}"
    draft = await create(c, h, base, "ifrs-" + kind, body)
    denied = await c.post(api + "/calculate/" + draft["id"], headers=h)
    assert denied.status_code == 409
    approved = await approve(c, h, reviewer[0], base, draft)
    response = await c.post(api + "/calculate/" + approved["id"], headers=h)
    assert response.status_code == 201, response.text
    run = response.json()
    if expected:
        assert Decimal(run["results"][key]) == Decimal(expected)
    proposed = await c.post(
        api + f"/runs/{run['id']}/propose-journal",
        headers=h,
        json={
            "profile_id": p["id"],
            "reference": "SYN-PROP",
            "debit_account": "500",
            "credit_account": "100",
            "adjustment_date": "2026-12-31",
            "rationale": "Synthetic selected accounts, independent review required",
        },
    )
    assert proposed.status_code == 201, proposed.text
    amount = Decimal("1000") if kind == "lease" else Decimal("65")
    assert Decimal(proposed.json()["body"]["legs"][0]["debit"]) == amount
    await approve(c, h, reviewer[0], base, proposed.json())
    atb = (await c.get(api + "/adjusted-trial-balance/" + p["id"], headers=h)).json()
    assert sum(Decimal(r["adjusted"]) for r in atb["lines"]) == 0
    assert next(Decimal(r["adjustment"]) for r in atb["lines"] if r["code"] == "500") == amount
    await action(c, reviewer[0], base, approved, "reopen")
    assert (await c.get(api + "/adjusted-trial-balance/" + p["id"], headers=h)).status_code == 409


async def test_ifrs_access_and_registry(environment):
    c = environment
    h, eid, base, reviewer, partner, p, mapping, note, ready = await prepared(c)
    api = f"/api/v1/ifrs/engagements/{eid}"
    auditor = await actor(h, "Auditor", "ifrs-no-permission")
    await grant(c, h, base, auditor)
    assert (await c.get(api + "/workspace", headers=auditor[0])).status_code == 403
    assert (await c.get(base + "/ifrs-note", headers=auditor[0])).status_code == 403
    denied = await c.post(
        base + "/ai-actions",
        headers=auditor[0],
        json={
            "task": "financial_statement_risks",
            "sources": [{"kind": "record", "id": note["id"]}],
        },
    )
    assert denied.status_code == 403
    available = (await c.get(base + "/linkable-sources", headers=auditor[0])).json()
    assert note["id"] not in {r["id"] for r in available["items"]}
    assert (
        await c.get(base + "/records/" + note["id"] + "/history", headers=auditor[0])
    ).status_code == 403
    standards = (await c.get("/api/v1/ifrs/standards", headers=h)).json()
    assert len(standards["items"]) == 35
    assert not standards["full_ifrs_text_licensed"]
    assert (
        next(s for s in standards["items"] if s["code"] == "IFRS 18")["effective_date"]
        == "2027-01-01"
    )


async def test_ai_disclosure_source_and_independent_review(environment):
    c = environment
    h, eid, base, reviewer, partner, p, mapping, note, ready = await prepared(c)
    api = f"/api/v1/ifrs/engagements/{eid}"
    from app.modules.ifrs.catalogue import AI_TASKS

    for task in AI_TASKS:
        response = await c.post(
            api + "/ai-actions",
            headers=h,
            json={"task": task, "sources": [{"kind": "record", "id": note["id"]}]},
        )
        assert response.status_code == 201, response.text
        obj = response.json()
        assert obj["body"]["output"]["citations"] == [note["id"]]
        assert obj["body"]["output"]["requires_human_review"]
        assert not obj["body"]["output"]["opinion_issued"]
        await action(c, h, base, obj, "approve", 403)
        reviewed = await action(c, reviewer[0], base, obj, "approve")
        assert reviewed["status"] == "APPROVED"
    unknown = await c.post(
        api + "/ai-actions",
        headers=h,
        json={"task": "disclosure_gaps", "sources": [{"kind": "record", "id": str(uuid.uuid4())}]},
    )
    assert unknown.status_code == 422


async def test_group_translation_eliminations_and_nci(environment):
    c = environment
    h, eid, base, reviewer, partner, p, mapping, note, ready = await prepared(c)

    async def post(path, body):
        r = await c.post("/api/v1/" + path, headers=h, json=body)
        assert r.status_code < 400, r.text
        return r.json()

    customer = await post("clients", {"code": "SYN-GROUP", "name": "SYNTHETIC subsidiary owner"})
    entity = await post(
        "entities",
        {
            "client_id": customer["id"],
            "name": "SYNTHETIC subsidiary",
            "country": "AE",
            "jurisdiction": "Synthetic",
            "functional_currency": "AED",
            "presentation_currency": "AED",
        },
    )
    period = await post(
        "financial-periods",
        {"entity_id": entity["id"], "start_date": "2026-01-01", "end_date": "2026-12-31"},
    )
    eng = await post(
        "engagements",
        {
            "entity_id": entity["id"],
            "period_id": period["id"],
            "name": "SYNTHETIC subsidiary reporting",
            "engagement_type": "External Audit",
        },
    )
    eid2 = eng["id"]
    base2 = f"/api/v1/engagements/{eid2}/audit"
    opts = {
        "client_id": customer["id"],
        "entity_id": entity["id"],
        "period_id": period["id"],
        "source_complete": True,
    }
    _, _, _, rev2, part2, p2, _, note2, ready2 = await prepared(c, (h, opts, eid2, base2), "-sub")
    members = []
    for en, ba, pr, rev, part, parent in [
        (eid, base, p, reviewer, partner, True),
        (eid2, base2, p2, rev2, part2, False),
    ]:
        run = await post(f"ifrs/engagements/{en}/financial-statements/{pr['id']}", None)
        package = await create(
            c,
            h,
            ba,
            "ifrs-financials",
            {"run_id": run["id"], "release_rationale": "Synthetic reviewed company report"},
        )
        package = await action(c, h, ba, package, "submit")
        package = await action(c, rev[0], ba, package, "approve")
        await action(c, part[0], ba, package, "approve")
        members.append(
            {
                "engagement_id": en,
                "financial_run_id": run["id"],
                "ownership": "1" if parent else "0.8",
                "power": True,
                "variable_returns": True,
                "ability_to_affect_returns": True,
                "control_rationale": "Synthetic documented control assessment",
                "closing_rate": "1" if parent else "2",
                "average_rate": "1" if parent else "1.5",
                "historical_rate": "1",
                "rate_source": "Synthetic independent rate fixture, no market claims",
                "rate_date": "2026-12-31",
                "acquisition_type": "parent" if parent else "business_combination",
                "accounting_policy": "Synthetic full aggregation",
                "consideration": "100" if not parent else "0",
                "net_assets_at_acquisition": "100" if not parent else "0",
                "nci_at_acquisition": "20" if not parent else "0",
            }
        )
    group = await ready(
        "consolidation",
        {
            "presentation_currency": "AED",
            "members": members,
            "eliminations": [
                {
                    "reference": "EL-1",
                    "debit_line": "400",
                    "credit_line": "500",
                    "amount": "10",
                    "reason": "Synthetic internal revenue/cost elimination",
                    "source_record_ids": [note["id"], note2["id"]],
                }
            ],
        },
    )
    run = await post(f"ifrs/engagements/{eid}/consolidation/{group['id']}", None)
    result = run["results"]
    assert Decimal(result["totals"]["assets"]) == 390
    assert Decimal(result["totals"]["profit"]) == 75
    assert Decimal(result["totals"]["nci"]) == 52
    assert Decimal(result["acquisition_schedule"]["goodwill_or_bargain_purchase_total"]) == 20
    assert result["validation"]["checks"][0]["passed"]
    assert not result["validation"]["ready"]  # Group cash-flow/notes release remains unsupported.
    assert (
        await c.get(f"/api/v1/ifrs/engagements/{eid}/runs/{run['id']}/export/pdf", headers=h)
    ).status_code == 200


async def test_comparatives_opening_consistency_and_tenant_rls(environment):
    c = environment
    h, eid, base, reviewer, partner, p, mapping, note, ready = await prepared(c)
    eng = (await c.get(f"/api/v1/engagements/{eid}", headers=h)).json()
    entity = (await c.get(f"/api/v1/entities/{eng['entity_id']}", headers=h)).json()
    period = await c.post(
        "/api/v1/financial-periods",
        headers=h,
        json={"entity_id": entity["id"], "start_date": "2025-01-01", "end_date": "2025-12-31"},
    )
    prior_eng = await c.post(
        "/api/v1/engagements",
        headers=h,
        json={
            "entity_id": entity["id"],
            "period_id": period.json()["id"],
            "name": "SYNTHETIC comparative",
            "engagement_type": "External Audit",
        },
    )
    prior_id = prior_eng.json()["id"]
    prior_base = f"/api/v1/engagements/{prior_id}/audit"
    await grant(c, h, prior_base, reviewer)
    opts = {
        "client_id": entity["client_id"],
        "entity_id": entity["id"],
        "period_id": period.json()["id"],
        "source_complete": True,
        "expected_rows": 6,
        "expected_debit": "170",
        "expected_credit": "170",
    }
    _, sid = await committed(c, h, opts, CSV.replace(b"2026", b"2025"))
    prior_profile = await create(
        c,
        h,
        prior_base,
        "ifrs-profile",
        {
            "snapshot_id": sid,
            "presentation_currency": "AED",
            "technical_validation": "Synthetic prior-period source",
        },
    )
    prior_profile = await approve(c, h, reviewer[0], prior_base, prior_profile)
    prior_mapping = await create(
        c,
        h,
        prior_base,
        "ifrs-mapping",
        {
            "profile_id": prior_profile["id"],
            "accounts": mapping["body"]["accounts"],
            "rationale": "Synthetic common line codes",
        },
    )
    await approve(c, h, reviewer[0], prior_base, prior_mapping)
    p = await action(c, reviewer[0], base, p, "reopen")
    body = {k: v for k, v in p["body"].items() if not k.startswith("review_")}
    body.update(
        comparative_snapshot_id=sid,
        comparative_profile_id=prior_profile["id"],
        comparative_engagement_id=prior_id,
    )
    updated = await c.patch(
        base + "/records/" + p["id"],
        headers=h,
        json={
            "version": p["version"],
            "body": body,
            "title": p["title"],
            "reference": p["reference"],
        },
    )
    assert updated.status_code == 200, updated.text
    p = await approve(c, h, reviewer[0], base, updated.json())
    api = f"/api/v1/ifrs/engagements/{eid}"
    report = await c.post(api + "/financial-statements/" + p["id"], headers=h)
    assert report.status_code == 201, report.text
    result = report.json()
    assert (
        next(
            Decimal(r["comparative"]) for r in result["results"]["lines"] if r["line_code"] == "100"
        )
        == 130
    )
    assert not next(
        check["passed"]
        for check in result["results"]["validation"]["checks"]
        if check["code"] == "comparative_opening_consistency"
    )
    from sqlalchemy import select, text
    from sqlalchemy.exc import DBAPIError

    from app.db.session import Session, tenant_context
    from app.modules.ifrs.models import CalculationRun

    async with Session() as db, db.begin():
        await tenant_context(db, uuid.uuid4())
        assert not (await db.scalars(select(CalculationRun))).all()
    async with Session() as db:
        with pytest.raises(DBAPIError):
            async with db.begin():
                await tenant_context(db, h["X-Tenant-ID"])
                await db.execute(
                    text("UPDATE ifrs_calculation_runs SET sha256='tampered' WHERE id=:id"),
                    {"id": uuid.UUID(result["id"])},
                )
    preparer = await actor(h, "Financial Reporting Preparer", "no-export")
    await grant(c, h, base, preparer)
    assert (
        await c.get(api + f"/runs/{result['id']}/export/pdf", headers=preparer[0])
    ).status_code == 403
