"""Real DB/source/review/export mechanics; fixtures do not qualify law or clients."""

import io
import os
from copy import deepcopy

import pytest
from openpyxl import load_workbook

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant, setup
from tests.qa_crud.test_country_workflows import (
    csv_bytes,
    decision,
    double_boundaries,
    execute,
    source,
)
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_msme_payments import TYPES, config, populations

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable database required"
)


@pytest.mark.parametrize("change", ["withdraw-source", "replace-context"])
async def test_msme_reviewed_sources_payment_result_export_and_withdrawal(
    environment, monkeypatch, change
):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "msme-independent-reviewer")
    await grant(c, h, base, reviewer)
    context_author = await actor(h, "Firm Administrator", "msme-context-author")
    await grant(c, h, base, context_author)
    prefix = f"/api/v1/intelligence/engagements/{eid}"
    catalogue = (await c.get(prefix + "/country-workflows", headers=h)).json()
    assert next(w for w in catalogue["items"] if w["id"] == "india-msme-payment-timing")[
        "available"
    ]
    assert "msme-invoices" in catalogue["source_contracts"]
    rows = populations()
    rows["invoices"][0].update(invoice_date="2026-04-01", delivery_date="2026-04-01")
    rows["bank"][0]["date"] = "2026-04-16"
    sources, contexts = {}, {}
    for role, records in rows.items():
        totals = (
            {"INR": "-100"}
            if role == "bank"
            else {"INR": "100"}
            if role in {"invoices", "allocations"}
            else {}
        )
        context_options = {}
        if role in {"assessments", "invoices"}:
            context_record = await create(
                c,
                context_author[0],
                base,
                "evidence",
                {"category": "Other", "retain_until": "2036-12-31"},
            )
            uploaded = await c.post(
                base + "/evidence-files/" + context_record["id"],
                headers=context_author[0],
                files={
                    "file": (
                        "SYNTHETIC-" + role + "-packet.txt",
                        (
                            "SYNTHETIC supporting packet for "
                            + role
                            + "; no legal/client qualification"
                        ).encode(),
                        "text/plain",
                    )
                },
            )
            assert uploaded.status_code == 201, uploaded.text
            contexts[role] = {
                "record_id": context_record["id"],
                "version_id": uploaded.json()["id"],
            }
            context_options = {
                "msme_context_evidence_version_id": uploaded.json()["id"],
                "msme_context_assessment": "SYNTHETIC supporting "
                + role
                + " facts in this retained packet, independent review still required",
            }
        sources[role] = await source(
            c, h, eid, records, "SYNTHETIC MSE " + role, TYPES[role], totals, **context_options
        )
        if role in contexts:
            assert (
                sources[role]["body"]["msme_evidence_context"]["evidence_version_id"]
                == contexts[role]["version_id"]
            )
            assert (await decision(c, context_author[0], eid, sources[role])).status_code == 403
    payload = {
        **config(),
        "as_of": "2026-04-30",
        "obligation_month_start": "2026-04",
        "obligation_month_end": "2026-04",
        "settlement_start": "2026-04-01",
        "source_ids": {role: r["id"] for role, r in sources.items()},
    }
    await execute(c, h, eid, "country-workflow", payload, failed="Independently review all")
    for role, obj in sources.items():
        reviewed = await decision(c, reviewer[0], eid, obj)
        assert reviewed.status_code == 201, reviewed.text
        sources[role] = reviewed.json()
    payload["source_ids"] = {role: r["id"] for role, r in sources.items()}
    result = await execute(c, h, eid, "country-workflow", payload)
    assert result["body"]["msme_document_binding"] == "RETAINED_DOCUMENT_BYTES_VERIFIED"
    assert len(result["body"]["retained_msme_contexts"]) == 2
    assert (await decision(c, context_author[0], eid, result)).status_code == 403
    row = result["body"]["rows"][0]
    assert row["due_date"] == "2026-04-16" and row["state"] == "MATCHED"
    assert row["late_paid_amount"] == row["overdue_unpaid_amount"] == "0"
    assert (await decision(c, h, eid, result)).status_code == 403
    reviewed = await decision(c, reviewer[0], eid, result)
    assert reviewed.status_code == 201, reviewed.text
    result = reviewed.json()
    exported = await c.get(prefix + f"/events/{result['id']}/export?format=xlsx", headers=h)
    assert exported.status_code == 200
    workbook = load_workbook(io.BytesIO(exported.content))
    exported_rows = list(workbook["Rows"].values)
    assert len(exported_rows) == 2
    due_column = exported_rows[0].index("due_date")
    assert exported_rows[1][due_column] == "2026-04-16"
    assert any("SYNTHETIC" in str(cell) for line in exported_rows for cell in line)
    original = deepcopy(result["body"])
    if change == "withdraw-source":
        rejected = await decision(c, reviewer[0], eid, sources["assessments"], "reject")
        assert rejected.status_code == 201, rejected.text
    else:
        replaced = await c.post(
            base + "/evidence-files/" + contexts["assessments"]["record_id"],
            headers=context_author[0],
            files={
                "file": (
                    "SYNTHETIC-packet-v2.txt",
                    b"SYNTHETIC changed eligibility packet",
                    "text/plain",
                )
            },
        )
        assert replaced.status_code == 201, replaced.text
        stale_source = (
            await c.get(prefix + "/events/" + sources["assessments"]["id"], headers=h)
        ).json()
        assert stale_source["freshness"] == "STALE"
    stale = (await c.get(prefix + "/events/" + result["id"], headers=h)).json()
    assert stale["freshness"] == "STALE" and stale["body"] == original


async def test_msme_sources_and_workflow_are_not_available_for_uae(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, _ = await setup(c)
    prefix = f"/api/v1/intelligence/engagements/{eid}"
    catalogue = (await c.get(prefix + "/country-workflows", headers=h)).json()
    assert not next(w for w in catalogue["items"] if w["id"] == "india-msme-payment-timing")[
        "available"
    ]
    assert not any(t.startswith("msme-") for t in catalogue["source_contracts"])
    await source(
        c,
        h,
        eid,
        populations()["invoices"],
        "SYNTHETIC wrong-country MSE",
        "msme-invoices",
        {"INR": "100"},
        failed="India engagement",
    )
    await execute(
        c,
        h,
        eid,
        "country-workflow",
        {**config(), "as_of": "2026-06-30"},
        failed="India engagement",
    )


async def test_resolved_msme_source_requires_distinct_context_bytes(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base = await india_context(c)
    rows = populations()["assessments"]
    await source(
        c,
        h,
        eid,
        rows,
        "SYNTHETIC missing context",
        "msme-supplier-assessments",
        {},
        failed="retained context document",
    )
    copy_record = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    copied = await c.post(
        base + "/evidence-files/" + copy_record["id"],
        headers=h,
        files={"file": ("SYNTHETIC copied packet.txt", csv_bytes(rows), "text/plain")},
    )
    assert copied.status_code == 201, copied.text
    await source(
        c,
        h,
        eid,
        rows,
        "SYNTHETIC duplicate context",
        "msme-supplier-assessments",
        {},
        msme_context_evidence_version_id=copied.json()["id"],
        msme_context_assessment="SYNTHETIC deliberate copy must not corroborate its own facts",
        failed="cannot corroborate itself",
    )
