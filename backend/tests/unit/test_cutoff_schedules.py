"""Independent period amounts and exact document allocation controls."""

import uuid
from copy import deepcopy

import pytest

from app.modules.country_workflows.audit_schemas import CutoffDocument
from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.review import approval_error
from app.modules.country_workflows.schemas import WorkflowInput
from tests.unit.test_shared_audit_workflows import source


def population(currency="AED"):
    document = dict(
        id="DOC-1",
        counterparty="VENDOR-1",
        reference="INV-1",
        currency=currency,
        amount="1200",
        invoice_date="2026-06-01",
        recognition_mode="explicit-schedule",
        recognition_basis="service-performed",
        evidence_reference="SERVICE-CONTRACT-1",
    )
    allocation = dict(
        id="ALLOC-1",
        document_id="DOC-1",
        counterparty="VENDOR-1",
        currency=currency,
        amount="100",
        recognition_date="2026-06-30",
        recognition_basis="service-performed",
        evidence_reference="REVIEWED-SERVICE-JUNE",
    )
    future = {
        **allocation,
        "id": "ALLOC-2",
        "amount": "1100",
        "recognition_date": "2027-05-31",
        "evidence_reference": "REVIEWED-FUTURE-SERVICE-SCHEDULE",
    }
    posting = dict(
        id="POST-1",
        document_id="DOC-1",
        allocation_id="ALLOC-1",
        counterparty="VENDOR-1",
        currency=currency,
        amount="100",
        posting_date="2026-06-30",
        account="EXP-SERVICES",
        journal_reference="JV-1",
        evidence_reference="LEDGER-LINE-1",
    )
    return dict(documents=[document], recognitions=[allocation, future], postings=[posting])


def run(rows, country="AE", **changes):
    types = dict(
        documents="cutoff-documents",
        recognitions="cutoff-recognition-lines",
        postings="cutoff-posting-lines",
    )
    data = WorkflowInput(
        workflow="expense-cutoff",
        source_ids={role: uuid.uuid4() for role in rows},
        period_start="2026-01-01",
        as_of="2026-06-30",
        review_through="2026-07-31",
        title="SYNTHETIC allocated expense cutoff",
        rationale="Independently assessed allocation and ledger source scope",
        **changes,
    )
    return calculate(
        data, country, {role: source(types[role], records) for role, records in rows.items()}
    )


@pytest.mark.parametrize("country,currency", [("AE", "AED"), ("IN", "INR")])
def test_only_allocated_current_period_expense_compares_to_current_postings(country, currency):
    rows = population(currency)
    original = deepcopy(rows)
    result = run(rows, country)
    assert rows == original and not result["blocked"] and result["exception_count"] == 0
    current, future = result["rows"]
    assert current["expected_period_amount"] == current["posted_period_amount"] == "100"
    assert future["amount"] == "1100" and future["expected_period_amount"] == "0"
    assert future["recognition_timing"] == "AFTER_REVIEW_WINDOW_ASSESSED_SCHEDULE"
    assert result["cutoff_document_controls"][0]["difference"] == "0"
    assert result["cutoff_schedule_contract"] == "explicit-cutoff-schedules/1"


@pytest.mark.parametrize("posted", [[], ["40"], ["100", "-100"], ["80", "40", "-20"]])
def test_partial_postings_and_reversals_preserve_every_original_link(posted):
    rows = population()
    template = rows["postings"][0]
    rows["postings"] = [
        {**template, "id": f"POST-{i}", "amount": amount} for i, amount in enumerate(posted)
    ]
    result = run(rows)
    current = result["rows"][0]
    expected = sum(map(int, posted))
    assert current["posted_period_amount"] == str(expected)
    assert len(current["posting_source_ids"]) == len(posted)
    assert len(result["cutoff_posting_links"]) == len(posted)
    assert current["state"] == (
        "MATCHED"
        if expected == 100
        else "UNRECORDED_LIABILITY"
        if expected == 0
        else "CUTOFF_POSTING_DIFFERENCE"
    )


def test_large_tolerance_does_not_hide_missing_or_wrong_period_postings():
    rows = population()
    rows["postings"] = []
    assert run(rows, tolerance="10000")["rows"][0]["state"] == "UNRECORDED_LIABILITY"
    rows["postings"] = [{**population()["postings"][0], "allocation_id": "ALLOC-2"}]
    result = run(rows, tolerance="10000")
    assert result["rows"][1]["state"] == "WRONG_PERIOD"


def test_subsequent_and_prior_period_postings_are_never_current_expense():
    for posting_date, state, field in [
        ("2026-07-10", "LATE_RECOGNITION", "subsequent_posted_amount"),
        ("2025-12-31", "WRONG_PERIOD", "prior_posted_amount"),
    ]:
        rows = population()
        rows["postings"][0]["posting_date"] = posting_date
        current = run(rows)["rows"][0]
        assert current["posted_period_amount"] == "0" and current[field] == "100"
        assert current["state"] == state and current["difference"] == "-100"


@pytest.mark.parametrize("amount", ["1099", "1101", "0"])
def test_document_allocation_control_is_exact_even_with_large_money_tolerance(amount):
    rows = population()
    rows["recognitions"][1]["amount"] = amount
    result = run(rows, tolerance="99999")
    assert (
        result["blocked"]
        and result["cutoff_document_controls"][0]["state"] == "CUTOFF_ALLOCATION_CONTROL_DIFFERENCE"
    )
    for row in result["rows"]:
        row["auditor_status"] = "EXCEPTION_DOCUMENTED"
    assert approval_error(result)


def test_missing_sources_and_empty_recognition_population_remain_incomplete():
    rows = population()
    missing = run({"documents": rows["documents"]})
    assert missing["blocked"] and missing["rows"][0]["state"] == "CUTOFF_ALLOCATION_SOURCES_MISSING"
    with pytest.raises(ValueError, match="Select both"):
        run({"documents": rows["documents"], "recognitions": rows["recognitions"]})
    rows["recognitions"] = []
    rows["postings"] = []
    assert run(rows)["blocked"]


@pytest.mark.parametrize(
    "role,field,value",
    [
        ("recognitions", "document_id", "UNKNOWN"),
        ("recognitions", "counterparty", "OTHER"),
        ("recognitions", "currency", "INR"),
        ("postings", "allocation_id", "UNKNOWN"),
        ("postings", "document_id", "OTHER"),
        ("postings", "counterparty", "OTHER"),
        ("postings", "currency", "INR"),
        ("postings", "posting_date", "2026-08-01"),
    ],
)
def test_exact_source_links_and_review_window_are_required(role, field, value):
    rows = population()
    rows[role][0][field] = value
    with pytest.raises(ValueError):
        run(rows)


def test_credit_notes_use_negative_allocations_and_remain_separate_from_invoices():
    rows = population()
    rows["documents"][0].update(document_kind="credit-note", amount="-1200")
    for row in rows["recognitions"] + rows["postings"]:
        row["amount"] = "-" + row["amount"]
    assert run(rows)["rows"][0]["state"] == "MATCHED"
    rows["postings"] = []
    assert run(rows)["rows"][0]["state"] == "UNRECORDED_CREDIT"
    rows["recognitions"][0]["amount"] = "100"
    with pytest.raises(ValueError, match="sign"):
        run(rows)


def test_explicit_schedule_cannot_silently_override_document_level_dates():
    for field in ("recognition_date", "posting_date"):
        with pytest.raises(ValueError, match="cannot compete"):
            CutoffDocument.model_validate({**population()["documents"][0], field: "2026-06-30"})
    with pytest.raises(ValueError, match="nonnegative"):
        CutoffDocument.model_validate({**population()["documents"][0], "amount": "-1"})


def test_duplicate_document_identity_cannot_double_the_assessed_invoice_population():
    rows = population()
    rows["documents"].append({**rows["documents"][0], "id": "DOC-DUPLICATE"})
    with pytest.raises(ValueError, match="Duplicate cutoff document"):
        run(rows)


def test_zero_document_needs_an_explicit_zero_allocation_and_observed_nil_posting_scope():
    rows = population()
    rows["documents"][0]["amount"] = "0"
    rows["recognitions"] = [{**rows["recognitions"][0], "amount": "0"}]
    rows["postings"] = []
    result = run(rows)
    assert not result["blocked"] and result["rows"][0]["posted_period_amount"] == "0"


def test_maximum_allocation_and_posting_populations_export_without_truncation():
    from tests.unit.test_xlsx_values import event, workbook

    rows = population()
    rows["documents"][0]["amount"] = "5000"
    allocation, posting = rows["recognitions"][0], rows["postings"][0]
    rows["recognitions"] = [
        {**allocation, "id": f"ALLOC-{i:04d}", "amount": "1"} for i in range(5000)
    ]
    rows["postings"] = [
        {**posting, "id": f"POST-{i:04d}", "allocation_id": f"ALLOC-{i:04d}", "amount": "1"}
        for i in range(5000)
    ]
    result = run(rows)
    assert not result["blocked"] and result["exception_count"] == 0
    assert len(result["rows"]) == len(result["cutoff_posting_links"]) == 5000
    book = workbook(event(**result))
    assert len(list(book["Rows"].values)) == 5001
    links = list(book["Cutoff posting links"].values)
    assert len(links) == 5001 and links[-1][0] == "POST-4999"
    book.close()


@pytest.mark.parametrize("country", ["AE", "IN"])
@pytest.mark.parametrize("case", ["split-reversal", "late-credit"])
def test_saved_country_examples_match_their_independent_controls_and_expected_period_amounts(
    country, case
):
    import json
    from pathlib import Path

    from app.modules.country_workflows.schemas import SourceInput
    from app.modules.country_workflows.sources import parse_csv

    folder = (
        Path(__file__).resolve().parents[3]
        / "docs/country-workflows/sample-inputs/SYNTHETIC-cutoff-schedules"
        / country
        / case
    )
    manifest = json.loads((folder / "scope-controls.json").read_text(encoding="utf-8"))
    sources = {}
    for role, controls in manifest["sources"].items():
        data = SourceInput(
            evidence_version_id=uuid.uuid4(), label="SYNTHETIC saved expense cutoff", **controls
        )
        sources[role] = parse_csv((folder / (role + ".csv")).read_bytes(), data)
    data = WorkflowInput(
        workflow="expense-cutoff",
        source_ids={role: uuid.uuid4() for role in sources},
        period_start=manifest["period_start"],
        as_of=manifest["as_of"],
        review_through=manifest["review_through"],
        title="SYNTHETIC saved expense cutoff",
        rationale="Independent saved synthetic source controls and expected period amounts",
    )
    result = calculate(data, country, sources)
    assert not result["blocked"]
    for field, value in manifest["expected_current"].items():
        assert result["rows"][0][field] == value
    for field, value in manifest["expected_future"].items():
        assert result["rows"][1][field] == value


def test_historical_single_date_source_rows_remain_usable_with_nil_optional_schedules():
    document = {
        **population()["documents"][0],
        "recognition_mode": "single-date",
        "recognition_date": "2026-06-30",
        "posting_date": "2026-06-30",
    }
    sources = {
        "documents": source("cutoff-documents", [document]),
        "recognitions": source("cutoff-recognition-lines", []),
        "postings": source("cutoff-posting-lines", []),
    }
    for field in ("recognition_mode", "document_kind"):
        sources["documents"]["rows"][0].pop(field)
    data = WorkflowInput(
        workflow="expense-cutoff",
        source_ids={role: uuid.uuid4() for role in sources},
        period_start="2026-01-01",
        as_of="2026-06-30",
        review_through="2026-07-31",
        title="SYN historic cutoff source",
        rationale="Historic canonical source rows predate the optional schedule fields",
    )
    result = calculate(data, "AE", sources)
    assert not result["blocked"] and result["rows"][0]["state"] == "MATCHED"
