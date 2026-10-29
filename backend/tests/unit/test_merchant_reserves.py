"""Independent reserve continuity examples; neither payout receipt nor legal qualification."""

import csv
import io
import json
from copy import deepcopy
from decimal import Decimal
from uuid import uuid4

import pytest
from openpyxl import load_workbook

from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.merchant_reserves import ROLES
from app.modules.country_workflows.merchant_settlements import COMPONENTS
from app.modules.country_workflows.review import approval_error
from app.modules.country_workflows.schemas import ROW_TYPES as ALL_ROWS
from app.modules.country_workflows.schemas import SourceInput, WorkflowInput
from app.modules.country_workflows.sources import parse_csv
from app.modules.intelligence.exports import render
from tests.unit.test_merchant_settlements import populations


def fixture(country="AE"):
    batch = populations(country)["processor"][0]
    common = {key: batch[key] for key in ("merchant", "processor", "currency")}
    return {
        "settlements": [batch],
        "movements": [
            {
                "id": "H1",
                **common,
                "settlement_id": "PAYOUT",
                "date": "2026-06-02",
                "sequence": 1,
                "kind": "HELD",
                "amount": "30",
                "reference": "HOLD-1",
                "evidence_reference": "SYN-STMT-1",
                "assessment": "Synthetic independently assessed reserve date and order",
            },
            {
                "id": "H2",
                **common,
                "settlement_id": "PAYOUT",
                "date": "2026-06-03",
                "sequence": 1,
                "kind": "HELD",
                "amount": "20",
                "reference": "HOLD-2",
                "evidence_reference": "SYN-STMT-1",
                "assessment": "Synthetic independently assessed reserve date and order",
            },
            {
                "id": "R1",
                **common,
                "settlement_id": "PAYOUT",
                "date": "2026-06-04",
                "sequence": 1,
                "kind": "RELEASED",
                "amount": "5",
                "reference": "RELEASE-1",
                "evidence_reference": "SYN-STMT-1",
                "assessment": "Synthetic independently assessed reserve date and order",
            },
        ],
        "balances": [
            {
                "id": "POSITION",
                **common,
                "period_start": "2026-06-01",
                "period_end": "2026-06-30",
                "opening_balance": "100",
                "closing_balance": "145",
                "ledger_account": "RESERVE-AR",
                "account_assessment": "Synthetic explicitly assessed processor reserve receivable mapping",
                "evidence_reference": "SYN-RESERVE-STMT",
            }
        ],
        "ledger": [
            {
                "id": "GL-OPEN",
                "account": "RESERVE-AR",
                "currency": batch["currency"],
                "side": "receivable",
                "as_of": "2026-05-31",
                "amount": "100",
            },
            {
                "id": "GL-CLOSE",
                "account": "RESERVE-AR",
                "currency": batch["currency"],
                "side": "receivable",
                "as_of": "2026-06-30",
                "amount": "145",
            },
        ],
    }


def controls(role, rows, currency="AED"):
    currencies = {row["currency"] for row in rows} or {currency}
    if role == "settlements":
        return (
            {
                "merchant_component_controls": {
                    c: {
                        f: str(sum((Decimal(r[f]) for r in rows if r["currency"] == c), Decimal(0)))
                        for f in COMPONENTS
                    }
                    for c in currencies
                }
            }
            if rows
            else {}
        )
    if role == "balances":
        return {
            "merchant_reserve_controls": {
                c: {
                    f: str(sum((Decimal(r[f]) for r in rows if r["currency"] == c), Decimal(0)))
                    for f in ("opening_balance", "closing_balance")
                }
                for c in currencies
            }
        }
    if role == "movements":
        return {
            "merchant_reserve_controls": {
                c: {
                    f: str(
                        sum(
                            (
                                Decimal(r["amount"])
                                for r in rows
                                if r["currency"] == c and r["kind"] == f.upper()
                            ),
                            Decimal(0),
                        )
                    )
                    for f in ("held", "released")
                }
                for c in currencies
            }
        }
    return {}


def source(role, rows, currency="AED", **overrides):
    fields = list(rows[0]) if rows else list(ALL_ROWS[ROLES[role]].model_fields)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    money = role in {"settlements", "ledger"}
    totals = (
        {
            c: str(sum((Decimal(r["amount"]) for r in rows if r["currency"] == c), Decimal(0)))
            for c in {r["currency"] for r in rows}
        }
        if money
        else {}
    )
    data = SourceInput(
        evidence_version_id=uuid4(),
        table_type=ROLES[role],
        label="SYNTHETIC reserve source",
        expected_rows=len(rows),
        nil_reason="Synthetic independently declared nil period activity" if not rows else None,
        control_totals=totals,
        **(controls(role, rows, currency) | overrides),
    )
    return parse_csv(stream.getvalue().encode(), data)


def payload(**changes):
    return WorkflowInput(
        **(
            dict(
                workflow="merchant-reserve-rollforward",
                source_ids={role: uuid4() for role in ROLES},
                period_start="2026-06-01",
                as_of="2026-06-30",
                currency="AED",
                title="SYNTHETIC reserve continuity",
                rationale="Synthetic independently reviewed component and reserve ledger controls",
            )
            | changes
        )
    )


def run(rows=None, country="AE", **changes):
    rows = rows if rows is not None else fixture(country)
    currency = "AED" if country == "AE" else "INR"
    return calculate(
        payload(**({"currency": currency} | changes)),
        country,
        {role: source(role, values, currency) for role, values in rows.items()},
    )


@pytest.mark.parametrize("country", ["AE", "IN"])
def test_split_holds_and_release_reconcile_to_statement_and_independent_ledger(country):
    rows = fixture(country)
    original = deepcopy(rows)
    out = run(rows, country)
    assert rows == original and not out["blocked"] and out["exception_count"] == 0
    position = next(r for r in out["rows"] if r["kind"] == "RESERVE_POSITION")
    assert position["computed_closing"] == "145" and position["closing_difference"] == "0"
    assert [r["balance_after"] for r in position["movement_trace"]] == ["130", "150", "145"]
    assert position["movement_ids"] == ["H1", "H2", "R1"]
    assert out["payment_state"] == "NOT_ASSESSED_BY_RESERVE_ROLLFORWARD"
    assert out["statutory_calculation_qualified"] is False


def test_equal_net_changes_do_not_hide_missing_hold_and_release_components():
    rows = fixture()
    rows["movements"][1]["amount"] = "15"
    rows["movements"] = rows["movements"][:2]
    out = run(rows)
    position = next(r for r in out["rows"] if r["kind"] == "RESERVE_POSITION")
    assert position["computed_closing"] == "145" and position["state"] == "MATCHED"
    batch = next(r for r in out["rows"] if r["kind"] == "BATCH_RESERVE_CONTROL")
    assert batch["issues"] == ["HELD_COMPONENT_DIFFERENCE", "RELEASED_COMPONENT_DIFFERENCE"]
    assert out["blocked"] and approval_error(out)


def test_interim_negative_reserve_cannot_be_hidden_by_a_later_hold():
    rows = fixture()
    rows["balances"][0].update(opening_balance="0", closing_balance="45")
    rows["ledger"][0]["amount"] = "0"
    rows["ledger"][1]["amount"] = "45"
    rows["movements"][2]["date"] = "2026-06-01"
    out = run(rows)
    position = next(r for r in out["rows"] if r["kind"] == "RESERVE_POSITION")
    assert position["computed_closing"] == "45" and position["closing_difference"] == "0"
    assert position["state"] == "RELEASE_EXCEEDS_AVAILABLE_RESERVE" and out["blocked"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("settlement_id", "UNKNOWN"),
        ("merchant", "OTHER"),
        ("processor", "OTHER"),
        ("currency", "USD"),
        ("date", "2026-07-01"),
    ],
)
def test_movements_cannot_cross_batch_party_currency_or_period(field, value):
    rows = fixture()
    rows["movements"][0][field] = value
    with pytest.raises(ValueError):
        run(rows)


@pytest.mark.parametrize(
    "field,value", [("id", "H1"), ("reference", "HOLD-1"), ("date", "2026-06-02")]
)
def test_duplicate_originals_or_chronology_cannot_be_summed(field, value):
    rows = fixture()
    rows["movements"][1][field] = value
    with pytest.raises(ValueError, match="Duplicate"):
        run(rows)


@pytest.mark.parametrize("index", [0, 1])
def test_opening_and_closing_ledger_must_each_match_not_only_net_movement(index):
    rows = fixture()
    rows["ledger"][index]["amount"] = "99"
    out = run(rows)
    ledger = next(r for r in out["rows"] if r["kind"] == "LEDGER_CONTROL")
    assert "LEDGER_DIFFERENCE" in ledger["state"] and out["blocked"]


def test_missing_ledger_opening_is_unavailable_not_zero():
    rows = fixture()
    rows["ledger"] = rows["ledger"][1:]
    out = run(rows)
    ledger = next(r for r in out["rows"] if r["kind"] == "LEDGER_CONTROL")
    assert ledger["ledger_difference"]["opening"] is None
    assert ledger["state"] == "OPENING_LEDGER_CONTROL_MISSING" and out["blocked"]


@pytest.mark.parametrize(
    "field,value",
    [("as_of", "2026-06-01"), ("side", "payable"), ("account", "UNSCOPED"), ("amount", "-1")],
)
def test_ledger_controls_require_exact_date_asset_sign_and_assessed_account(field, value):
    rows = fixture()
    rows["ledger"][0][field] = value
    with pytest.raises(ValueError, match="Ledger controls"):
        run(rows)


def test_statement_balance_and_net_arithmetic_discrepancies_block_approval():
    rows = fixture()
    rows["balances"][0]["closing_balance"] = "144"
    rows["settlements"][0]["amount"] = "799"
    out = run(rows)
    assert out["blocked"] and approval_error(out)
    assert any("PROCESSOR_NET_ARITHMETIC_DIFFERENCE" in r["issues"] for r in out["rows"])
    assert any("RESERVE_ROLLFORWARD_DIFFERENCE" in r["issues"] for r in out["rows"])


@pytest.mark.parametrize(
    "role,declared",
    [
        ("movements", {"AED": {"held": "45", "released": "0"}}),
        ("movements", {}),
        ("balances", {"AED": {"opening_balance": "0", "closing_balance": "45"}}),
    ],
)
def test_independent_gross_and_point_balance_controls_cannot_be_replaced_by_net(role, declared):
    with pytest.raises(ValueError):
        source(role, fixture()[role], merchant_reserve_controls=declared)


def test_explicit_nil_movement_and_batch_populations_preserve_known_opening_balance():
    rows = fixture()
    rows["movements"] = []
    rows["settlements"] = []
    rows["balances"][0]["closing_balance"] = "100"
    rows["ledger"][1]["amount"] = "100"
    out = run(rows)
    assert not out["blocked"] and out["rows"][0]["computed_closing"] == "100"


@pytest.mark.parametrize(
    "changes",
    [
        {"period_start": None},
        {"period_start": "2026-07-01"},
        {"tolerance": "1"},
        {"date_tolerance": 1},
    ],
)
def test_reserve_window_and_controls_are_explicit_and_exact(changes):
    with pytest.raises(ValueError):
        payload(**changes)


def test_country_rule_metadata_is_not_inferred_from_matching_amounts():
    rows = fixture()
    rows["settlements"][0]["tax_country"] = "IN"
    with pytest.raises(ValueError, match="country assessment"):
        run(rows)


def test_blank_assessment_or_invalid_control_currency_is_not_review_evidence():
    rows = fixture()
    rows["movements"][0]["assessment"] = " " * 20
    with pytest.raises(ValueError):
        source("movements", rows["movements"])
    with pytest.raises(ValueError):
        source(
            "movements",
            fixture()["movements"],
            merchant_reserve_controls={"aed": {"held": "50", "released": "5"}},
        )


def test_old_or_unversioned_reserve_result_cannot_be_approved():
    assert approval_error(
        {"workflow": "merchant-reserve-rollforward", "rows": [], "blocked": False}
    )


def test_shared_ledger_account_does_not_pool_available_reserve_between_merchants():
    rows = fixture()
    other = deepcopy(rows)
    for role in ("settlements", "movements", "balances"):
        for row in other[role]:
            row["id"] += "-OTHER"
            row["merchant"] = "OTHER"
            if role == "movements":
                row["settlement_id"] += "-OTHER"
        rows[role].extend(other[role])
    rows["ledger"][0]["amount"] = "200"
    rows["ledger"][1]["amount"] = "290"
    out = run(rows)
    assert not out["blocked"]
    assert len([r for r in out["rows"] if r["kind"] == "RESERVE_POSITION"]) == 2
    ledger = next(r for r in out["rows"] if r["kind"] == "LEDGER_CONTROL")
    assert ledger["processor_closing"] == "290"
    # Move the other merchant's opening to the first merchant without changing pooled GL.
    rows["balances"][0]["opening_balance"] = "200"
    rows["balances"][0]["closing_balance"] = "245"
    rows["balances"][1]["opening_balance"] = "0"
    rows["balances"][1]["closing_balance"] = "45"
    rows["movements"][-1]["date"] = "2026-06-01"
    blocked = run(rows)
    assert blocked["blocked"]
    assert any("RELEASE_EXCEEDS_AVAILABLE_RESERVE" in row["issues"] for row in blocked["rows"])


def test_large_export_preserves_each_movement_and_original_result_without_cell_truncation():
    rows = fixture()
    example = rows["movements"][0]
    rows["movements"] = [
        {
            **example,
            "id": f"H{i}",
            "sequence": i + 1,
            "amount": "0.125",
            "reference": "H" + str(i) + "x" * 100,
        }
        for i in range(400)
    ] + [fixture()["movements"][-1]]
    body = run(rows)
    assert not body["blocked"]
    assert len(json.dumps(body["rows"][0]["movement_trace"])) > 32767
    original = deepcopy(body)
    event = {
        "id": "SYNTHETIC-RESERVE",
        "kind": "country-workflow",
        "version": 1,
        "sha256": "a" * 64,
        "created_at": "2026-06-30T00:00:00Z",
        "body": body,
        "dependencies": [],
    }
    content, _ = render(event, "xlsx")
    workbook = load_workbook(io.BytesIO(content))
    exported = list(workbook["Reserve movements"].values)
    assert len(exported) == 402
    records = [dict(zip(exported[0], row, strict=True)) for row in exported[1:]]
    assert records[399]["reference"] == "H399" + "x" * 100
    assert records[-1]["balance_after"] == "145.000"
    assert body == original
