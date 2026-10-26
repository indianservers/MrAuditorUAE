"""Exact offsite quantities, condition, ownership scope and retained correspondence."""

import csv
import io
import uuid
from copy import deepcopy

import pytest

from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.inventory_custody import CustodyConfirmation
from app.modules.country_workflows.review import approval_error
from app.modules.country_workflows.schemas import ROW_TYPES, SourceInput, WorkflowInput
from app.modules.country_workflows.sources import parse_csv


def population():
    scope = dict(custodian="WAREHOUSE-1", site="OFFSITE-1", sku="SKU-1", lot="LOT-1", uom="KG")
    position = dict(
        id="POS-1",
        **scope,
        as_of="2026-06-30",
        quantity="10",
        ownership="entity-owned",
        title_reference="SYN-TITLE-REF-1",
    )
    response = dict(
        id="LETTER-1",
        position_id="POS-1",
        **scope,
        as_of="2026-06-30",
        requested_quantity="10",
        response_quantity="10",
        status="received",
        condition="good",
        held_for_entity="yes",
        requested_on="2026-07-01",
        responded_on="2026-07-05",
        contact_verified=True,
        independently_received=True,
        request_evidence_version_id=str(uuid.uuid4()),
        request_source_sha256="a" * 64,
        request_reference="SYN-REQUEST-1",
        response_evidence_version_id=str(uuid.uuid4()),
        response_source_sha256="b" * 64,
        response_reference="SYN-RESPONSE-1",
        scope_assessment="Fictional assessed full offsite quantity and condition; no title authenticity conclusion",
    )
    return dict(positions=[position], responses=[response])


def controls(rows, responses=False):
    return [
        {
            **{field: row[field] for field in ("custodian", "site", "sku", "lot", "uom")},
            "position_id": row["position_id"] if responses else row["id"],
            "quantity": row["requested_quantity"] if responses else row["quantity"],
            "response_quantity": row.get("response_quantity") if responses else None,
        }
        for row in rows
    ]


def source(role, rows, **options):
    kind = (
        "inventory-custody-confirmations" if role == "responses" else "inventory-custody-positions"
    )
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=list(ROW_TYPES[kind].model_fields))
    writer.writeheader()
    writer.writerows(rows)
    data = SourceInput(
        evidence_version_id=uuid.uuid4(),
        table_type=kind,
        label="SYNTHETIC offsite custody source",
        expected_rows=len(rows),
        control_totals={},
        nil_reason="Independently assessed fictional nil source population; not a nil inventory conclusion"
        if not rows
        else None,
        **{"custody_quantity_controls": controls(rows, role == "responses"), **options},
    )
    return parse_csv(out.getvalue().encode(), data)


def run(rows, country="AE", **changes):
    data = WorkflowInput(
        workflow="inventory-custody-confirmations",
        source_ids={role: uuid.uuid4() for role in rows},
        as_of="2026-06-30",
        review_through="2026-07-15",
        title="SYNTHETIC external custody quantities",
        rationale="Independent offsite book quantities, correspondence and condition assessment",
        **changes,
    )
    return calculate(data, country, {role: source(role, records) for role, records in rows.items()})


def followup(letter):
    alternative = letter["status"] in {"pending", "undeliverable", "unreliable"}
    return {
        **letter,
        "followup_evidence_version_id": str(uuid.uuid4()),
        "followup_source_sha256": "c" * 64,
        "followup_kind": "alternative-procedures" if alternative else "exception-investigation",
        "followup_on": "2026-07-10",
        "followup_reference": "SYN-FOLLOWUP-1",
        "followup_assessment": "Fictional procedures separately assessed; no automatic title, condition or existence assurance",
    }


def pending(letter, status="pending"):
    return {
        **letter,
        "status": status,
        "response_quantity": None,
        "condition": None,
        "held_for_entity": "unknown",
        "responded_on": None,
        "response_evidence_version_id": None,
        "response_source_sha256": None,
        "response_reference": "",
        "independently_received": False,
    }


@pytest.mark.parametrize("country", ["AE", "IN"])
def test_exact_quantity_and_condition_response_keeps_custody_separate_from_title(country):
    rows = population()
    original = deepcopy(rows)
    result = run(rows, country)
    assert rows == original and not result["blocked"] and result["exception_count"] == 0
    row = result["rows"][0]
    assert row["quantity_difference"] == "0" and row["book_quantity"] == "10"
    assert row["declared_ownership"] == "entity-owned" and row["held_for_entity"] == "yes"
    assert result["custody_confirmation_contract"] == "offsite-inventory-confirmations/1"


def test_confirmed_zero_is_distinct_from_missing_reply_and_unknown_book_population():
    rows = population()
    rows["positions"][0]["quantity"] = "0"
    rows["responses"][0].update(requested_quantity="0", response_quantity="0")
    assert run(rows)["rows"][0]["response_quantity"] == "0"
    rows["responses"] = []
    assert run(rows)["blocked"] and run(rows)["rows"][0]["response_quantity"] is None
    rows = population()
    rows["positions"] = []
    result = run(rows)
    assert (
        result["blocked"]
        and result["rows"][0]["book_quantity"] is None
        and result["rows"][0]["quantity_difference"] is None
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("uom", "EA"),
        ("custodian", "OTHER"),
        ("site", "OTHER"),
        ("lot", "OTHER"),
        ("sku", "OTHER"),
        ("as_of", "2026-06-29"),
        ("requested_quantity", "9"),
    ],
)
def test_scope_differences_never_produce_a_quantity_comparison(field, value):
    rows = population()
    rows["responses"][0][field] = value
    result = run(rows)
    assert result["blocked"] and result["rows"][0]["state"] == "CUSTODY_SCOPE_MISMATCH"
    assert result["rows"][0]["quantity_difference"] is None


@pytest.mark.parametrize(
    "change",
    [
        {"response_quantity": "10.01"},
        {"condition": "damaged"},
        {"condition": "unknown"},
        {"status": "disputed"},
    ],
)
def test_quantity_or_condition_exceptions_need_retained_followup_and_independent_disposition(
    change,
):
    rows = population()
    rows["responses"][0].update(change)
    result = run(rows, tolerance="100000")
    assert result["blocked"] and result["rows"][0]["state"] == "CUSTODY_EXCEPTION_FOLLOWUP_MISSING"
    rows["responses"][0] = followup(rows["responses"][0])
    result = run(rows, tolerance="100000")
    assert (
        not result["blocked"] and result["rows"][0]["state"] == "CUSTODY_EXCEPTION_REQUIRES_REVIEW"
    )
    assert approval_error(result)
    result["rows"][0]["auditor_status"] = "EXCEPTION_DOCUMENTED"
    assert approval_error(result) is None


@pytest.mark.parametrize("status", ["pending", "undeliverable", "unreliable"])
def test_nonresponses_and_unreliable_replies_never_become_confirmations(status):
    rows = population()
    rows["responses"][0] = (
        pending(rows["responses"][0], status)
        if status != "unreliable"
        else {**rows["responses"][0], "status": "unreliable", "contact_verified": False}
    )
    assert run(rows)["blocked"]
    rows["responses"][0] = followup(rows["responses"][0])
    result = run(rows)
    assert not result["blocked"] and result["rows"][0]["quantity_difference"] is None
    assert result["rows"][0]["state"] == "CUSTODY_ALTERNATIVE_PROCEDURES_REQUIRE_REVIEW"


@pytest.mark.parametrize("ownership", ["third-party-owned", "unconfirmed"])
def test_external_custody_is_not_an_entity_ownership_assertion(ownership):
    rows = population()
    rows["positions"][0]["ownership"] = ownership
    rows["responses"][0] = followup(rows["responses"][0])
    result = run(rows)
    assert result["blocked"] and result["rows"][0]["state"] == "ENTITY_OWNERSHIP_NOT_DECLARED"
    result["rows"][0]["auditor_status"] = "EXCEPTION_DOCUMENTED"
    assert approval_error(result)


@pytest.mark.parametrize(
    "field,value",
    [
        ("held_for_entity", "unknown"),
        ("held_for_entity", "no"),
        ("independently_received", False),
        ("contact_verified", False),
    ],
)
def test_received_reply_requires_assessed_contact_and_direct_receipt_and_held_for_entity(
    field, value
):
    rows = population()
    rows["responses"][0][field] = value
    assert run(rows)["blocked"] and run(rows)["rows"][0]["quantity_difference"] is None


def test_independent_quantity_controls_bind_actual_response_and_every_physical_scope():
    rows = population()
    declared = controls(rows["responses"], True)
    declared[0]["response_quantity"] = "9"
    with pytest.raises(ValueError, match="quantity controls must match"):
        source("responses", rows["responses"], custody_quantity_controls=declared)
    with pytest.raises(ValueError, match="quantity controls must match"):
        source("positions", rows["positions"], custody_quantity_controls=[])
    rows["positions"].append({**rows["positions"][0], "id": "DUPLICATE"})
    with pytest.raises(ValueError, match="one current custody"):
        run(rows)


def test_empty_populations_do_not_qualify_nil_offsite_inventory():
    result = run({"positions": [], "responses": []})
    assert result["blocked"] and result["rows"][0]["state"] == "CUSTODY_POPULATION_MISSING"


@pytest.mark.parametrize(
    "change",
    [
        {"response_quantity": None},
        {"condition": None},
        {"response_source_sha256": None},
        {"responded_on": "2026-06-30"},
    ],
)
def test_written_reply_contract_requires_both_quantity_and_condition_and_bound_documents(change):
    with pytest.raises(ValueError):
        CustodyConfirmation.model_validate({**population()["responses"][0], **change})


def test_dates_after_review_through_do_not_enter_quantity_comparisons():
    rows = population()
    rows["responses"][0]["responded_on"] = "2026-07-16"
    result = run(rows)
    assert result["blocked"] and result["rows"][0]["state"] == "OUTSIDE_REVIEW_WINDOW"
    assert result["rows"][0]["quantity_difference"] is None


@pytest.mark.parametrize("status", ["received", "pending"])
def test_a_preissued_request_does_not_assert_future_holdings_before_the_reporting_date(status):
    rows = population()
    rows["responses"][0]["requested_on"] = "2026-06-20"
    if status == "pending":
        rows["responses"][0] = followup(pending(rows["responses"][0]))
    assert not run(rows)["blocked"]
    if status == "received":
        rows["responses"][0]["responded_on"] = "2026-06-29"
        with pytest.raises(ValueError):
            run(rows)


def test_maximum_custody_populations_retain_every_quantity_control_and_document_link_in_export():
    from tests.unit.test_xlsx_values import event, workbook

    template = population()
    position = template["positions"][0]
    letter = template["responses"][0]
    rows = dict(
        positions=[{**position, "id": f"POS-{i:04d}", "sku": f"SKU-{i:04d}"} for i in range(5000)],
        responses=[
            {
                **letter,
                "id": f"LETTER-{i:04d}",
                "position_id": f"POS-{i:04d}",
                "sku": f"SKU-{i:04d}",
            }
            for i in range(5000)
        ],
    )
    result = run(rows)
    assert not result["blocked"] and result["exception_count"] == 0 and len(result["rows"]) == 5000
    book = workbook(event(**result))
    documents = list(book["Custody documents"].values)
    assert len(documents) == 10001 and documents[-1][1] == "POS-4999"
    quantity_controls = list(book["Custody quantity controls"].values)
    assert len(quantity_controls) == 10001 and quantity_controls[-1][1] == "POS-4999"
    book.close()


@pytest.mark.parametrize("country", ["AE", "IN"])
@pytest.mark.parametrize("case", ["received", "pending", "zero-held"])
def test_saved_custody_examples_parse_with_actual_published_document_bytes(country, case):
    import hashlib
    import json
    from pathlib import Path

    folder = (
        Path(__file__).resolve().parents[3]
        / "docs/country-workflows/sample-inputs/SYNTHETIC-inventory-custody"
        / country
        / case
    )
    manifest = json.loads((folder / "scope-controls.json").read_text(encoding="utf-8"))
    defaults = {}
    for role, document in manifest["supporting_documents"].items():
        assert (
            hashlib.sha256((folder / document["filename"]).read_bytes()).hexdigest()
            == document["sha256"]
        )
        defaults[role + "_evidence_version_id"] = str(uuid.uuid4())
        defaults[role + "_source_sha256"] = document["sha256"]
    sources = {}
    for role, kind in (
        ("positions", "inventory-custody-positions"),
        ("responses", "inventory-custody-confirmations"),
    ):
        data = SourceInput(
            evidence_version_id=uuid.uuid4(),
            table_type=kind,
            label="SYNTHETIC saved custody example",
            expected_rows=manifest["source_rows"][role],
            control_totals={},
            custody_quantity_controls=manifest["custody_quantity_controls_by_source"][role],
        )
        sources[role] = parse_csv(
            (folder / (role + ".csv")).read_bytes(), data, defaults if role == "responses" else None
        )
    data = WorkflowInput(
        workflow=manifest["workflow"],
        source_ids={role: uuid.uuid4() for role in sources},
        as_of=manifest["as_of"],
        review_through=manifest["review_through"],
        title="SYNTHETIC saved custody example",
        rationale="Independent example source controls and retained document hashes",
    )
    result = calculate(data, country, sources)
    row = result["rows"][0]
    assert result["blocked"] == manifest["expected"]["blocked"]
    for field in ("state", "quantity_difference", "response_quantity"):
        assert row[field] == manifest["expected"][field]


def test_explicit_none_held_reply_and_not_applicable_condition_are_not_an_unanswered_request():
    rows = population()
    rows["positions"][0]["quantity"] = "0"
    rows["responses"][0].update(
        requested_quantity="0",
        response_quantity="0",
        condition="not-applicable",
        held_for_entity="none-held",
    )
    result = run(rows)
    assert not result["blocked"] and result["rows"][0]["state"] == "MATCHED"
    assert result["rows"][0]["response_quantity"] == "0"
    rows["responses"][0] = pending(rows["responses"][0])
    assert run(rows)["blocked"] and run(rows)["rows"][0]["response_quantity"] is None


@pytest.mark.parametrize(
    "change", [{"held_for_entity": "none-held"}, {"condition": "not-applicable"}]
)
def test_none_held_or_not_applicable_cannot_clear_positive_written_quantities(change):
    with pytest.raises(ValueError, match="explicit written zero"):
        CustodyConfirmation.model_validate({**population()["responses"][0], **change})


def test_none_held_against_positive_books_preserves_the_full_quantity_difference():
    rows = population()
    rows["responses"][0].update(
        response_quantity="0", condition="not-applicable", held_for_entity="none-held"
    )
    result = run(rows)
    assert result["blocked"] and result["rows"][0]["quantity_difference"] == "-10"
