"""Retained native source, separate crosswalk, review, full export and staleness."""

import io
import os
from decimal import Decimal

import pytest
from openpyxl import load_workbook

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute
from tests.qa_crud.test_country_workflows import source as csv_source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_india_27q_native import controls27, options27, original27
from tests.unit.test_india_withholding_native import controls as legacy_controls
from tests.unit.test_india_withholding_native import options as legacy_options
from tests.unit.test_india_withholding_native import original as legacy_original

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable DB required"
)


def controls(form="26Q"):
    return controls27() if form == "27Q" else legacy_controls(form)


def options(form="26Q", **changes):
    return options27(**changes) if form == "27Q" else legacy_options(form, **changes)


def original(form="26Q"):
    return original27() if form == "27Q" else legacy_original(form)


async def upload(c, h, base, name, content):
    record = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    response = await c.post(
        base + "/evidence-files/" + record["id"],
        headers=h,
        files={"file": (name, content, "text/plain")},
    )
    assert response.status_code == 201, response.text
    return record, response.json()


@pytest.mark.parametrize("form", ["26Q", "27EQ", "27Q"])
async def test_native_regular_statement_with_crosswalk_retains_complete_reported_observations(
    environment, monkeypatch, form
):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "native-withholding-reviewer")
    await grant(c, h, base, reviewer)
    _, file = await upload(c, h, base, "public-issuer-" + form + "-sample.txt", original(form))
    crosswalk, document = await upload(
        c,
        h,
        base,
        "SYNTHETIC-independent-crosswalk.txt",
        b"SYNTHETIC independent original-party to transaction and section crosswalk; no client or legal qualification",
    )
    declared = controls(form)
    declared["crosswalk_document_version_id"] = document["id"]
    payload = options(
        form, evidence_version_id=file["id"], native_withholding_controls=declared
    ).model_dump(mode="json")
    source = await execute(c, h, eid, "workflow-source", payload)
    metadata = source["body"]["native_metadata"]
    assert metadata["crosswalk_document_sha256"] == document["sha256"]
    assert metadata["filing_or_acknowledgment"] == "NOT_EVIDENCED"
    assert source["body"]["allowed_source_roles"] == ["reported"]
    assert any(
        dep["type"] == "evidence" and dep["sha256"] == document["sha256"]
        for dep in source["dependencies"]
    )
    assert (await decision(c, h, eid, source)).status_code == 403
    response = await decision(c, reviewer[0], eid, source)
    assert response.status_code == 201, response.text
    reviewed = response.json()
    path = f"/api/v1/intelligence/engagements/{eid}/events/{reviewed['id']}"
    export = await c.get(path + "/export?format=xlsx", headers=h)
    assert export.status_code == 200, export.text
    book = load_workbook(io.BytesIO(export.content), read_only=True)
    links = list(book["Withholding party links"].values)
    assert len(links) == declared["party_count"] + 1
    records = [dict(zip(links[0], row, strict=True)) for row in links[1:]]
    assert records[-1]["party_key"] == f"1/1/{declared['party_count']}"
    assert sum(Decimal(row["total_tax"]) for row in records) == Decimal(declared["income_tax"])
    if form == "27Q":
        assert [r["recorded_rate_basis"] for r in records] == ["B", "B"]
        assert [r["nature_of_remittance_code"] for r in records] == ["21", "49"]
        assert [r["residence_country_code"] for r in records] == ["113", "113"]
        assert records[0]["foreign_tax_identifier"] is None
        assert metadata["nonresident_treaty_and_residence_qualification"] == "NOT_PERFORMED"
    challans = list(book["Withholding challans"].values)
    assert len(challans) == 2
    declared_challan = dict(zip(challans[0], challans[1], strict=True))
    assert declared_challan["bsr_or_form24g_reference"] == (
        "0000809" if form == "26Q" else "0000525" if form == "27Q" else "0000897"
    )
    assert Decimal(declared_challan["gross_deposit"]) == Decimal(declared["challan_deposit"])
    book.close()
    rule_record, rule_file = await upload(
        c,
        h,
        base,
        "SYNTHETIC-independent-expected-assessment.txt",
        b"SYNTHETIC independently specified public sample expected schedule; fictional assessed rules only, no legal or client qualification",
    )
    selected = {"reported": reviewed["id"]}
    expected_amounts = (
        ["1000", "500", "200", "200"]
        if form == "26Q"
        else ["11000", "155000"]
        if form == "27Q"
        else ["100"] * 10
    )
    month = "2020-04" if form == "26Q" else "2019-12" if form == "27Q" else "2020-10"
    due = "2020-05-07" if form == "26Q" else "2020-01-07" if form == "27Q" else "2020-11-07"
    paid = "2020-05-01" if form == "26Q" else "2020-01-01" if form == "27Q" else "2020-11-01"
    for role in ("expected", "withheld", "deposited"):
        rows = [
            {
                "id": f"SYN-{role}-{i}",
                "registration": "MUMN77777A",
                "counterparty": ["GHSPL9563J", "HNSPL7485K"][i - 1]
                if form == "27Q"
                else "AAAPA1234A",
                "legal_role": "collector" if form == "27EQ" else "deductor",
                "tax_kind": "TCS" if form == "27EQ" else "TDS",
                "rule_reference": "SYN-NR-ASSESSED-SECTION"
                if form == "27Q"
                else "SYN-ASSESSED-SECTION",
                "tax_year_start": "2019-04-01" if form == "27Q" else "2020-04-01",
                "tax_year_end": "2020-03-31" if form == "27Q" else "2021-03-31",
                "period": month,
                "transaction_reference": f"SYN-NR-{i}" if form == "27Q" else f"SYN-ASSESSMENT-{i}",
                "transaction_date": month + ("-10" if form == "27Q" else "-01"),
                "currency": "INR",
                "amount": amount,
                "record_status": "current",
                "source_reference": f"SYN-independent-{role}-{i}",
                "source_version": "independently-specified-fixture-1",
                "due_date": due,
                "payment_date": paid if role == "deposited" else None,
                **(
                    {
                        "assessment_kind": "rule",
                        "assessment_period_start": "2019-04-01" if form == "27Q" else "2020-04-01",
                        "assessment_period_end": "2020-03-31" if form == "27Q" else "2021-03-31",
                    }
                    if role == "expected"
                    else {}
                ),
            }
            for i, amount in enumerate(expected_amounts, 1)
        ]
        imported = await csv_source(
            c,
            h,
            eid,
            rows,
            "SYNTHETIC independent " + role,
            "withholding-records",
            {"INR": declared["income_tax"]},
            **({"rule_document_version_id": rule_file["id"]} if role == "expected" else {}),
        )
        accepted = await decision(c, reviewer[0], eid, imported)
        assert accepted.status_code == 201, accepted.text
        selected[role] = accepted.json()["id"]
    comparison = await execute(
        c,
        h,
        eid,
        "country-workflow",
        {
            "workflow": "india-withholding-liability",
            "withholding_role": "collector" if form == "27EQ" else "deductor",
            "source_ids": selected,
            "as_of": "2026-06-30",
            "title": "SYNTHETIC independently controlled native statement comparison",
            "rationale": "Independently specified per-party expected amounts versus original uploaded prepared-statement observations",
        },
    )
    assert comparison["body"]["blocked"] is False
    assert len(comparison["body"]["rows"]) == len(expected_amounts)
    assert all(row["state"] == "MATCHED" for row in comparison["body"]["rows"])
    replacement = await c.post(
        base + "/evidence-files/" + crosswalk["id"],
        headers=h,
        files={
            "file": (
                "SYNTHETIC-crosswalk-corrected.txt",
                b"SYNTHETIC corrected crosswalk requires new source assessment and review",
                "text/plain",
            )
        },
    )
    assert replacement.status_code == 201, replacement.text
    historical = (await c.get(path, headers=h)).json()
    assert historical["freshness"] == "STALE"
    assert historical["body"] == reviewed["body"] and historical["version"] == reviewed["version"]
    affected = (
        await c.get(f"/api/v1/intelligence/engagements/{eid}/events/{comparison['id']}", headers=h)
    ).json()
    assert affected["freshness"] == "STALE"
    assert affected["body"] == comparison["body"] and affected["version"] == comparison["version"]
    await execute(c, h, eid, "workflow-source", payload, failed="superseded")


@pytest.mark.parametrize("cloned", [False, True])
async def test_native_statement_cannot_supply_its_own_crosswalk(environment, monkeypatch, cloned):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base = await india_context(c)
    _, file = await upload(c, h, base, "public-issuer-26Q-sample.txt", original())
    declared = controls()
    context = file
    if cloned:
        _, context = await upload(c, h, base, "same-content-other-record.txt", original())
    declared["crosswalk_document_version_id"] = context["id"]
    await execute(
        c,
        h,
        eid,
        "workflow-source",
        options(evidence_version_id=file["id"], native_withholding_controls=declared).model_dump(
            mode="json"
        ),
        failed="separate independent",
    )


async def test_native_crosswalk_quarantine_is_not_bypassed(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base = await india_context(c)
    _, file = await upload(c, h, base, "public-26Q-original.txt", original())
    double_boundaries(monkeypatch, scan="QUARANTINED")
    _, crosswalk = await upload(
        c,
        h,
        base,
        "SYNTHETIC-quarantined-crosswalk.txt",
        b"SYNTHETIC quarantined mapping must not be used",
    )
    declared = controls()
    declared["crosswalk_document_version_id"] = crosswalk["id"]
    await execute(
        c,
        h,
        eid,
        "workflow-source",
        options(evidence_version_id=file["id"], native_withholding_controls=declared).model_dump(
            mode="json"
        ),
        failed="quarantined",
    )
