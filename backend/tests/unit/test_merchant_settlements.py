"""Independent synthetic gross/net examples, not tax or client qualification."""

import csv
import io
import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.merchant_settlements import COMPONENTS, ROLES
from app.modules.country_workflows.schemas import SourceInput, WorkflowInput
from app.modules.country_workflows.sources import parse_csv


def populations(country="AE"):
    currency = "AED" if country == "AE" else "INR"
    common = dict(merchant="SHOP", processor="PSP", batch="BATCH-1", currency=currency)
    return {
        "books": [
            dict(
                common,
                id="SALE",
                reference="ORDER-1",
                date="2026-06-01",
                kind="SALE",
                amount="1000",
                evidence_reference="SYNTHETIC order",
            ),
            dict(
                common,
                id="REFUND",
                reference="REFUND-1",
                date="2026-06-02",
                kind="REFUND",
                amount="100",
                evidence_reference="SYNTHETIC refund",
            ),
            dict(
                common,
                id="DISPUTE",
                reference="CASE-1",
                date="2026-06-02",
                kind="CHARGEBACK",
                amount="20",
                evidence_reference="SYNTHETIC chargeback",
            ),
        ],
        "processor": [
            dict(
                common,
                id="PAYOUT",
                period_start="2026-06-01",
                period_end="2026-06-02",
                settlement_date="2026-06-03",
                sales="1000",
                refunds="100",
                chargebacks="20",
                fees="30",
                fee_tax="2",
                withholding="3",
                reserve_held="50",
                reserve_released="5",
                amount="800",
                tax_country=country,
                fee_tax_kind="UAE_VAT" if country == "AE" else "INDIA_GST",
                tax_assessment_reference="SYNTHETIC assessment",
                evidence_reference="SYNTHETIC statement",
                assessment="Independently assessed synthetic component facts; no legal rate assertion",
            )
        ],
        "bank": [
            dict(
                id="BANK",
                account="ACCT",
                reference="PSP-PAYOUT",
                date="2026-06-03",
                amount="800",
                currency=currency,
            )
        ],
        "allocations": [
            dict(
                id="LINK",
                settlement_id="PAYOUT",
                bank_transaction_id="BANK",
                currency=currency,
                amount="800",
                evidence_reference="SYNTHETIC remittance",
                assessment="Synthetic exact batch and bank movement evidence",
            )
        ],
    }


def sources(population):
    output = {}
    for role, rows in population.items():
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        totals = {}
        for row in rows:
            totals[row["currency"]] = totals.get(row["currency"], Decimal(0)) + Decimal(
                row["amount"]
            )
        controls = {}
        if role == "processor":
            controls = {
                currency: {
                    field: sum(
                        (Decimal(row[field]) for row in rows if row["currency"] == currency),
                        Decimal(0),
                    )
                    for field in COMPONENTS
                }
                for currency in totals
            }
        data = SourceInput(
            evidence_version_id=uuid.uuid4(),
            table_type=ROLES[role],
            label="SYNTHETIC merchant source",
            expected_rows=len(rows),
            control_totals=totals,
            merchant_component_controls=controls,
        )
        output[role] = parse_csv(buffer.getvalue().encode(), data)
    return output


def payload(**changes):
    value = dict(
        workflow="merchant-settlement-bridge",
        source_ids={role: str(uuid.uuid4()) for role in ROLES},
        as_of="2026-06-30",
        period_start="2026-06-01",
        account="ACCT",
        currency="AED",
        title="SYNTHETIC merchant bridge",
        rationale="Synthetic independent books, processor and bank assessment",
    )
    value.update(changes)
    return value


def run(population=None, country="AE", **changes):
    return calculate(
        WorkflowInput(**payload(**changes)), country, sources(population or populations(country))
    )


@pytest.mark.parametrize("country,currency", [("AE", "AED"), ("IN", "INR")])
def test_gross_refunds_chargebacks_fees_tax_reserves_and_net(country, currency):
    result = run(country=country, currency=currency)
    row = result["rows"][0]
    assert row["expected_net"] == "800" and row["bank_allocated"] == "800"
    assert row["book_differences"] == {"sales": "0", "refunds": "0", "chargebacks": "0"}
    assert row["state"] == "MATCHED" and not result["blocked"]
    assert result["statutory_calculation_qualified"] is False
    assert result["merchant_settlement_contract"] == "explicit-gross-net-bank/1"


def test_two_partial_bank_receipts_preserve_exact_links():
    p = populations()
    p["bank"][0]["amount"] = "500"
    p["bank"].append(dict(p["bank"][0], id="BANK-2", amount="300", date="2026-06-04"))
    p["allocations"][0]["amount"] = "500"
    p["allocations"].append(
        dict(p["allocations"][0], id="LINK-2", bank_transaction_id="BANK-2", amount="300")
    )
    row = run(p)["rows"][0]
    assert row["state"] == "MATCHED" and row["allocation_ids"] == ["LINK", "LINK-2"]


@pytest.mark.parametrize("field", ["sales", "refunds", "chargebacks"])
def test_components_cannot_offset_each_other(field):
    p = populations()
    p["processor"][0][field] = str(Decimal(p["processor"][0][field]) + 1)
    result = run(p)
    assert result["blocked"]
    assert any(issue.startswith("BOOK_") for issue in result["rows"][0]["issues"])
    assert "PROCESSOR_NET_ARITHMETIC_DIFFERENCE" in result["rows"][0]["issues"]


def test_unpaid_processor_and_unallocated_bank_are_separate_exceptions():
    p = populations()
    p["allocations"][0]["amount"] = "700"
    result = run(p)
    assert result["blocked"] and len(result["rows"]) == 2
    assert result["rows"][0]["bank_difference"] == "100"
    assert result["rows"][1]["amount"] == "100"


@pytest.mark.parametrize(
    "change,error",
    [
        (lambda p: p["allocations"][0].update(amount="801"), "exceeds"),
        (lambda p: p["allocations"][0].update(amount="-800"), "direction"),
        (lambda p: p["allocations"][0].update(bank_transaction_id="MISSING"), "missing exact"),
        (
            lambda p: p["allocations"].append(dict(p["allocations"][0], id="DUP")),
            "Duplicate merchant allocation",
        ),
        (lambda p: p["bank"][0].update(account="OTHER"), "mixes accounts"),
        (lambda p: p["bank"][0].update(date="2026-06-02"), "precedes"),
        (lambda p: p["bank"][0].update(date="2026-07-01"), "outside"),
        (lambda p: p["books"][0].update(batch="OTHER"), "no independently reported"),
        (lambda p: p["books"][0].update(date="2026-05-01"), "outside"),
        (lambda p: p["books"].append(dict(p["books"][0], id="DUP")), "Duplicate original"),
        (
            lambda p: p["processor"].append(dict(p["processor"][0], id="DUP")),
            "Duplicate merchant/processor",
        ),
        (lambda p: p["processor"][0].update(fee_tax_kind="INDIA_GST"), "engagement country"),
    ],
)
def test_invalid_scopes_do_not_produce_approvable_results(change, error):
    p = populations()
    change(p)
    with pytest.raises(ValueError, match=error):
        run(p)


def test_independent_component_control_rechecked_on_calculation():
    s = sources(populations())
    s["processor"]["rows"][0]["sales"] = "1001"
    with pytest.raises(ValueError, match="component control"):
        calculate(WorkflowInput(**payload()), "AE", s)


def test_missing_component_is_not_assumed_zero():
    p = populations()
    del p["processor"][0]["reserve_released"]
    from app.modules.country_workflows.merchant_settlements import MerchantSettlement

    with pytest.raises(ValidationError):
        MerchantSettlement(**p["processor"][0])


def test_negative_settlement_supports_explicit_debit_not_positive_receipt():
    p = populations()
    p["books"] = [dict(p["books"][1], amount="100")]
    p["processor"][0].update(
        sales="0",
        refunds="100",
        chargebacks="0",
        fees="0",
        fee_tax="0",
        withholding="0",
        reserve_held="0",
        reserve_released="0",
        amount="-100",
        fee_tax_kind="NO_TAX_ASSESSED",
    )
    p["bank"][0]["amount"] = "-100"
    p["allocations"][0]["amount"] = "-100"
    assert run(p)["rows"][0]["state"] == "MATCHED"


def test_committed_books_are_not_independent_bank_evidence():
    s = sources(populations())
    s["bank"]["parser_version"] = "committed-ledger-1"
    with pytest.raises(ValueError, match="independent bank"):
        calculate(WorkflowInput(**payload()), "AE", s)


def test_two_batches_can_share_one_exact_bank_movement_without_double_counting():
    p = populations()
    for row in list(p["books"]):
        p["books"].append(dict(row, id=row["id"] + "-2", batch="BATCH-2"))
    p["processor"].append(dict(p["processor"][0], id="PAYOUT-2", batch="BATCH-2"))
    p["bank"][0]["amount"] = "1600"
    p["allocations"].append(dict(p["allocations"][0], id="LINK-2", settlement_id="PAYOUT-2"))
    result = run(p)
    assert not result["blocked"] and len(result["rows"]) == 2
    assert [row["bank_allocated"] for row in result["rows"]] == ["800", "800"]


@pytest.mark.parametrize("field", COMPONENTS)
def test_each_independent_processor_control_is_required(field):
    s = sources(populations())
    del s["processor"]["merchant_component_controls"]["AED"][field]
    with pytest.raises(ValueError, match="every gross-to-net component"):
        calculate(WorkflowInput(**payload()), "AE", s)


def test_balanced_gross_and_refund_inflation_cannot_hide_behind_correct_net():
    p = populations()
    p["processor"][0].update(sales="1100", refunds="200")
    result = run(p)
    assert result["blocked"] and result["rows"][0]["expected_net"] == "800"
    assert result["rows"][0]["issues"] == ["BOOK_SALE_DIFFERENCE", "BOOK_REFUND_DIFFERENCE"]


@pytest.mark.parametrize(
    "change",
    [
        {"period_start": None},
        {"period_start": "2026-07-01"},
        {"account": ""},
        {"tolerance": "1"},
        {"date_tolerance": 1},
    ],
)
def test_explicit_scope_required(change):
    data = payload()
    data.update(change)
    with pytest.raises(ValidationError):
        WorkflowInput(**data)
