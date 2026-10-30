"""Synthetic FIFO arithmetic and controls; no physical or legal qualification."""

import csv
import io
from copy import deepcopy
from decimal import localcontext
from uuid import uuid4

import pytest

from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.schemas import SourceInput, WorkflowInput
from app.modules.country_workflows.sources import parse_csv


def event(identifier, kind, quantity, unit_cost=None, day="2026-06-01", sequence=0, **changes):
    return {
        "id": identifier,
        "site": "SYN-SITE",
        "sku": "SYN-SKU",
        "lot": "SYN-LOT",
        "uom": "PCS",
        "currency": "AED",
        "date": day,
        "sequence": sequence,
        "kind": kind,
        "quantity": quantity,
        "unit_cost": unit_cost,
        "source_evidence_version_id": str(uuid4()),
        "source_sha256": "a" * 64,
        "evidence_reference": "SYN-COST-POLICY-PACKET",
        "assessment": "SYNTHETIC independently assessed movement and FIFO cost policy",
        **changes,
    }


def control(**changes):
    return {
        "site": "SYN-SITE",
        "sku": "SYN-SKU",
        "lot": "SYN-LOT",
        "uom": "PCS",
        "currency": "AED",
        "expected_rows": 3,
        "opening_quantity": "10",
        "receipt_quantity": "10",
        "issue_quantity": "15",
        "opening_cost": "100",
        "receipt_cost": "200",
        "rounding_places": 2,
        "rounding_method": "HALF_UP",
        **changes,
    }


def book(**changes):
    return {
        "id": "SYN-BOOK",
        "account": "INV",
        "site": "SYN-SITE",
        "sku": "SYN-SKU",
        "lot": "SYN-LOT",
        "uom": "PCS",
        "currency": "AED",
        "quantity": "5",
        "unit_cost": "20",
        "unit_nrv": "25",
        "ownership": "owned",
        "condition": "good",
        "count_date": "2026-06-30",
        **changes,
    }


def source(table, rows, controls):
    params = {
        "evidence_version_id": str(uuid4()),
        "table_type": table,
        "label": "SYNTHETIC FIFO input",
        "expected_rows": len(rows),
        "control_totals": {},
    }
    if table == "inventory-cost-movements":
        params["inventory_fifo_controls"] = controls
    else:
        params["inventory_quantity_controls"] = [
            {
                **{k: r[k] for k in ["site", "sku", "lot", "uom", "currency"]},
                "expected_rows": 1,
                "positive_quantity": r["quantity"],
                "negative_quantity": "0",
            }
            for r in rows
        ]
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return parse_csv(out.getvalue().encode(), SourceInput.model_validate(params))


def run(events=None, books=None, controls=None, country="AE", **changes):
    events = (
        events
        if events is not None
        else [
            event("OPEN", "opening", "10", "10"),
            event("RECEIPT", "receipt", "10", "20", day="2026-06-02"),
            event("ISSUE", "issue", "15", day="2026-06-03"),
        ]
    )
    books = books if books is not None else [book()]
    controls = controls if controls is not None else [control()]
    sources = {
        "movements": source("inventory-cost-movements", events, controls),
        "books": source("stock", books, []),
    }
    data = WorkflowInput.model_validate(
        {
            "workflow": "inventory-fifo-cost",
            "source_ids": {role: str(uuid4()) for role in sources},
            "period_start": "2026-06-01",
            "as_of": "2026-06-30",
            "tolerance": "0",
            "date_tolerance": 0,
            "inventory_scope_assessment": "SYNTHETIC independently selected FIFO, gross-cost scope and rounding assessment",
            "title": "Synthetic FIFO",
            "rationale": "Independent input controls and closing book cost",
            **changes,
        }
    )
    return calculate(data, country, sources)


@pytest.mark.parametrize("country,currency", [("AE", "AED"), ("IN", "INR")])
def test_fifo_allocates_oldest_layers_without_cross_country_defaults(country, currency):
    events = [
        event("OPEN", "opening", "10", "10", currency=currency),
        event("RECEIPT", "receipt", "10", "20", day="2026-06-02", currency=currency),
        event("ISSUE", "issue", "15", day="2026-06-03", currency=currency),
    ]
    retained = deepcopy(events)
    out = run(
        list(reversed(events)), [book(currency=currency)], [control(currency=currency)], country
    )
    assert events == retained and not out["blocked"]
    assert out["rows"][0]["raw_fifo_closing_cost"] == "100"
    assert out["rows"][0]["expected_closing_quantity"] == "5"
    assert out["rows"][0]["covered_issue_cost"] == "200"
    assert out["rows"][0]["raw_cost_rollforward_difference"] == "0"
    assert out["rows"][0]["raw_book_gross_cost"] == "100"
    assert out["rows"][0]["fifo_rounding_difference"] == "0.00"
    assert out["fifo_closing_layers"][0]["currency"] == currency
    assert out["inventory_fifo_controls"][0]["expected_rows"] == 3
    assert [
        (x["layer_source_row_id"], x["quantity"], x["cost"]) for x in out["fifo_allocations"]
    ] == [("OPEN", "10", "100"), ("RECEIPT", "5", "100")]
    assert out["statutory_calculation_qualified"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected_rows", 2),
        ("opening_quantity", "11"),
        ("receipt_quantity", "9"),
        ("issue_quantity", "14"),
        ("opening_cost", "101"),
        ("receipt_cost", "199"),
    ],
)
def test_independent_controls_do_not_net_incompatible_components(field, value):
    with pytest.raises(ValueError, match="Independent FIFO"):
        run(controls=[control(**{field: value})])


def test_later_receipts_do_not_retroactively_cost_an_earlier_short_issue():
    out = run(
        [
            event("O", "opening", "1", "10"),
            event("I", "issue", "2", day="2026-06-02"),
            event("R", "receipt", "3", "20", day="2026-06-03"),
        ],
        [book(quantity="2")],
        [
            control(
                opening_quantity="1",
                receipt_quantity="3",
                issue_quantity="2",
                opening_cost="10",
                receipt_cost="60",
            )
        ],
    )
    assert out["blocked"] and out["rows"][0]["raw_fifo_closing_cost"] is None
    assert out["rows"][0]["expected_closing_quantity"] == "2"
    assert out["fifo_event_costs"][1]["unallocated_issue_quantity"] == "1"
    assert out["fifo_closing_layers"][0]["basis"] == "INCOMPLETE_PROVISIONAL"
    from app.modules.country_workflows.review import approval_error

    assert (
        approval_error(
            {
                **out,
                "workflow": "inventory-fifo-cost",
                "inventory_fifo_document_binding": "RETAINED_DOCUMENT_BYTES_VERIFIED",
            }
        )
        is not None
    )


def test_fifo_verification_bound_does_not_silently_drop_movements():
    from app.modules.country_workflows.inventory_fifo import verify_controls

    with pytest.raises(ValueError, match="between 1 and 5000"):
        verify_controls([{}] * 5001, [control()])
    with pytest.raises(ValueError, match="between 1 and 5000"):
        verify_controls([], [])


@pytest.mark.parametrize("method,expected", [("HALF_UP", "0.01"), ("HALF_EVEN", "0.00")])
def test_rounding_is_declared_and_raw_cost_is_retained(method, expected):
    out = run(
        [event("O", "opening", "1", "0.005")],
        [book(quantity="1", unit_cost="0")],
        [
            control(
                expected_rows=1,
                opening_quantity="1",
                receipt_quantity="0",
                issue_quantity="0",
                opening_cost="0.005",
                receipt_cost="0",
                rounding_method=method,
            )
        ],
    )
    assert out["rows"][0]["raw_fifo_closing_cost"] == "0.005"
    assert out["rows"][0]["rounded_fifo_closing_cost"] == expected
    assert out["blocked"] is (method == "HALF_UP")
    assert out["rows"][0]["fifo_rounding_difference"] == (
        "0.005" if method == "HALF_UP" else "-0.005"
    )
    assert out["rows"][0]["raw_cost_rollforward_difference"] == "0.000"


@pytest.mark.parametrize("day", ["2026-06-01T00:00:00", "2026-06-01 ", "2026-6-1", 1780272000])
def test_movement_dates_cannot_be_timestamp_or_coerced_calendar_values(day):
    from app.modules.country_workflows.inventory_fifo import CostMovement

    with pytest.raises(ValueError, match="exact calendar date"):
        CostMovement.model_validate(event("O", "opening", "1", "10", day=day))


@pytest.mark.parametrize("sequence", [True, 1.0, "1.0", " 1", "-1"])
def test_fifo_sequence_requires_exact_whole_number_ordinal(sequence):
    from app.modules.country_workflows.inventory_fifo import CostMovement

    with pytest.raises(ValueError, match="whole-number ordinal"):
        CostMovement.model_validate(event("O", "opening", "1", "10", sequence=sequence))


@pytest.mark.parametrize(
    "changes,exception",
    [
        ({"count_date": "2026-06-29"}, "BOOK_DATE_OWNERSHIP_OR_QUANTITY_REQUIRES_REVIEW"),
        ({"ownership": "third-party"}, "BOOK_DATE_OWNERSHIP_OR_QUANTITY_REQUIRES_REVIEW"),
        ({"quantity": "4"}, "CLOSING_QUANTITY_DIFFERENCE"),
        ({"unit_cost": "19"}, "FIFO_GROSS_COST_DIFFERENCE"),
    ],
)
def test_closing_book_exceptions_block_release(changes, exception):
    out = run(books=[book(**changes)])
    assert out["blocked"]
    assert exception in out["rows"][0]["exceptions"]


@pytest.mark.parametrize("partition", ["site", "sku", "lot", "uom", "currency"])
def test_fifo_never_offsets_separate_stock_partitions(partition):
    other = "USD" if partition == "currency" else "OTHER"
    out = run(books=[book(**{partition: other})])
    assert out["blocked"] and len(out["rows"]) == 2
    assert {issue for row in out["rows"] for issue in row["exceptions"]} == {
        "MISSING_MOVEMENT_POPULATION",
        "MISSING_CLOSING_BOOK_POSITION",
    }


def test_receipt_order_ties_are_not_resolved_by_file_order_or_identifier():
    with pytest.raises(ValueError, match="ambiguous"):
        run(
            [
                event("O", "opening", "10", "10"),
                event("R", "receipt", "10", "20"),
                event("I", "issue", "15", day="2026-06-03"),
            ]
        )


def test_high_precision_costs_ignore_the_callers_decimal_context():
    with localcontext() as context:
        context.prec = 6
        out = run(
            [event("O", "opening", "1.23456789", "9.87654321")],
            [book(quantity="1.23456789", unit_cost="9.87654321")],
            [
                control(
                    expected_rows=1,
                    opening_quantity="1.23456789",
                    receipt_quantity="0",
                    issue_quantity="0",
                    opening_cost="12.1932631112635269",
                    receipt_cost="0",
                    rounding_places=8,
                )
            ],
        )
    assert out["rows"][0]["raw_fifo_closing_cost"] == "12.1932631112635269"
    assert not out["blocked"]


def test_exact_5000_event_population_has_complete_allocations():
    events = [event(f"O{i}", "opening", "1", "1", sequence=i) for i in range(2500)] + [
        event(f"I{i}", "issue", "1", day="2026-06-02", sequence=i) for i in range(2500)
    ]
    out = run(
        events,
        [book(quantity="0", unit_cost="1")],
        [
            control(
                expected_rows=5000,
                opening_quantity="2500",
                receipt_quantity="0",
                issue_quantity="2500",
                opening_cost="2500",
                receipt_cost="0",
            )
        ],
    )
    assert (
        not out["blocked"]
        and len(out["fifo_allocations"]) == 2500
        and len(out["fifo_event_costs"]) == 5000
    )
    assert out["fifo_closing_layers"] == []
