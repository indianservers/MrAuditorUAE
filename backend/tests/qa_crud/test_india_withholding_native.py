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
from tests.unit.test_india_form138_native import controls138, options138, original138, synthetic138
from tests.unit.test_india_form143_native import controls143, options143, original143, synthetic143
from tests.unit.test_india_withholding_native import controls as legacy_controls
from tests.unit.test_india_withholding_native import options as legacy_options
from tests.unit.test_india_withholding_native import original as legacy_original

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable DB required"
)


def controls(form="26Q"):
    if form == "138":
        return controls138()
    if form == "143":
        return controls143()
    return controls27() if form == "27Q" else legacy_controls(form)


def options(form="26Q", **changes):
    if form == "138":
        if "native_withholding_controls" in changes:
            changes["form138_controls"] = changes.pop("native_withholding_controls")
        return options138(**changes)
    if form == "143":
        if "native_withholding_controls" in changes:
            changes["form143_controls"] = changes.pop("native_withholding_controls")
        return options143(**changes)
    return options27(**changes) if form == "27Q" else legacy_options(form, **changes)


def original(form="26Q"):
    if form == "138":
        return synthetic138()
    if form == "143":
        return synthetic143()
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


@pytest.mark.parametrize("form", ["143", "138"])
@pytest.mark.parametrize(
    "scenario",
    ["incomplete_original", "self_crosswalk", "cloned_crosswalk", "quarantined_crosswalk"],
)
async def test_dated_form143_source_cannot_create_a_result_from_missing_or_unverified_evidence(
    environment, monkeypatch, scenario, form
):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base = await india_context(c)
    content = (
        (original143() if form == "143" else original138())
        if scenario == "incomplete_original"
        else original(form)
    )
    _, file = await upload(
        c,
        h,
        base,
        f"unchanged-public-{form}.txt"
        if scenario == "incomplete_original"
        else f"SYNTHETIC-explicit-completion-{form}.txt",
        content,
    )
    if scenario == "self_crosswalk":
        document = file
    else:
        if scenario == "quarantined_crosswalk":
            double_boundaries(monkeypatch, scan="INFECTED")
        _, document = await upload(
            c,
            h,
            base,
            "SYNTHETIC-crosswalk.txt",
            content
            if scenario == "cloned_crosswalk"
            else b"SYNTHETIC separate assessed transaction and collection-code crosswalk",
        )
    declared = {**controls(form), "crosswalk_document_version_id": document["id"]}
    payload = options(
        form, evidence_version_id=file["id"], native_withholding_controls=declared
    ).model_dump(mode="json")
    reason = (
        ("identifiers" if form == "143" else "year")
        if scenario == "incomplete_original"
        else "quarantined"
        if scenario == "quarantined_crosswalk"
        else "separate independent"
    )
    job = await execute(c, h, eid, "workflow-source", payload, failed=reason)
    assert job["result_id"] is None


@pytest.mark.parametrize("form", ["26Q", "27EQ", "27Q", "143", "138"])
async def test_native_regular_statement_with_crosswalk_retains_complete_reported_observations(
    environment, monkeypatch, form
):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "native-withholding-reviewer")
    await grant(c, h, base, reviewer)
    _, file = await upload(
        c,
        h,
        base,
        ("SYNTHETIC-explicit-completion-" if form in {"143", "138"} else "public-issuer-")
        + form
        + "-sample.txt",
        original(form),
    )
    crosswalk, document = await upload(
        c,
        h,
        base,
        "SYNTHETIC-independent-crosswalk.txt",
        b"SYNTHETIC independent original-party to transaction and section crosswalk; no client or legal qualification",
    )
    declared = controls(form)
    tax_total = (
        declared["tax_deducted"]
        if form == "138"
        else declared["tax_collected"]
        if form == "143"
        else declared["income_tax"]
    )
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
    assert sum(Decimal(row["total_tax"]) for row in records) == Decimal(tax_total)
    if form == "143":
        assert records[0]["recorded_deposited_flag"] == "Y"
        assert records[0]["recorded_section202_opt_out"] == "N"
        assert "income_tax" not in records[0] and metadata["workbook_version"] == "1.1"
    if form == "138":
        assert [r["recorded_deposit_date"] for r in records] == ["2026-05-09"] * 2
        assert [r["recorded_deposited_flag"] for r in records] == ["Y"] * 2
        assert "recorded_rate" not in records[0] and "income_tax" not in records[0]
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
        "2000090"
        if form == "138"
        else "5000032"
        if form == "143"
        else "0000809"
        if form == "26Q"
        else "0000525"
        if form == "27Q"
        else "0000897"
    )
    assert Decimal(declared_challan["gross_deposit"]) == Decimal(declared["challan_deposit"])
    if form == "143":
        assert (
            declared_challan["recorded_payment_mode"] == "B"
            and declared_challan["ddo_serial"] == "00001"
        )
        assert (
            declared_challan["allocated_interest"]
            == declared_challan["allocated_other"]
            == "1000.00"
        )
        assert "book_entry_flag" not in declared_challan
    if form == "138":
        assert declared_challan["recorded_penalty"] == "100.00"
        assert declared_challan["allocated_penalty"] == "100.00"
        assert "recorded_other" not in declared_challan
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
        ["2000", "2000"]
        if form == "138"
        else ["700"]
        if form == "143"
        else ["1000", "500", "200", "200"]
        if form == "26Q"
        else ["11000", "155000"]
        if form == "27Q"
        else ["100"] * 10
    )
    month = (
        "2026-05"
        if form in {"143", "138"}
        else "2020-04"
        if form == "26Q"
        else "2019-12"
        if form == "27Q"
        else "2020-10"
    )
    due = (
        "2026-06-07"
        if form in {"143", "138"}
        else "2020-05-07"
        if form == "26Q"
        else "2020-01-07"
        if form == "27Q"
        else "2020-11-07"
    )
    paid = (
        "2026-06-01"
        if form in {"143", "138"}
        else "2020-05-01"
        if form == "26Q"
        else "2020-01-01"
        if form == "27Q"
        else "2020-11-01"
    )
    for role in ("expected", "withheld", "deposited"):
        rows = [
            {
                "id": f"SYN-{role}-{i}",
                "registration": declared["tan"],
                "counterparty": ["BRNPA7789J", "BRNPA3344H"][i - 1]
                if form == "138"
                else "BRNPA7455N"
                if form == "143"
                else ["GHSPL9563J", "HNSPL7485K"][i - 1]
                if form == "27Q"
                else "AAAPA1234A",
                "legal_role": "collector" if form in {"27EQ", "143"} else "deductor",
                "tax_kind": "TCS" if form in {"27EQ", "143"} else "TDS",
                "rule_reference": "SYN-ASSESSED-SALARY"
                if form == "138"
                else "SYN-NR-ASSESSED-SECTION"
                if form == "27Q"
                else "SYN-ASSESSED-SECTION",
                "tax_year_start": "2026-04-01"
                if form in {"143", "138"}
                else "2019-04-01"
                if form == "27Q"
                else "2020-04-01",
                "tax_year_end": "2027-03-31"
                if form in {"143", "138"}
                else "2020-03-31"
                if form == "27Q"
                else "2021-03-31",
                "period": month,
                "transaction_reference": f"SYN-SALARY-{i}"
                if form == "138"
                else f"SYN-NR-{i}"
                if form == "27Q"
                else f"SYN-ASSESSMENT-{i}",
                "transaction_date": month
                + ("-06" if form == "138" else "-10" if form == "27Q" else "-01"),
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
                        "assessment_period_start": "2026-04-01"
                        if form in {"143", "138"}
                        else "2019-04-01"
                        if form == "27Q"
                        else "2020-04-01",
                        "assessment_period_end": "2027-03-31"
                        if form in {"143", "138"}
                        else "2020-03-31"
                        if form == "27Q"
                        else "2021-03-31",
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
            {"INR": tax_total},
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
            "withholding_role": "collector" if form in {"27EQ", "143"} else "deductor",
            "source_ids": selected,
            "as_of": "2026-06-30",
            "title": "SYNTHETIC independently controlled native statement comparison",
            "rationale": "Independently specified per-party expected amounts versus original uploaded prepared-statement observations",
        },
    )
    assert comparison["body"]["blocked"] is False, comparison["body"]
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
