"""Withholding identities survive pooled and split cash settlement."""

from copy import deepcopy
from uuid import uuid4

import pytest

from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.review import approval_error
from app.modules.country_workflows.schemas import Obligation, WorkflowInput
from app.modules.country_workflows.withholding_obligations import (
    WithholdingObligationInput,
    source_rows,
)
from app.modules.country_workflows.withholding_provisions import saved_withdrawn_expectation
from tests.unit.test_dues_allocations import example, parameters
from tests.unit.test_withholding_workflows import record


def records(purpose="expected", legal_role="deductor"):
    base = record(
        payment_date=None,
        due_date="2026-06-30",
        counterparty="SYN-SAME-PARTY",
        legal_role=legal_role,
        tax_kind="TDS" if legal_role == "deductor" else "TCS",
        assessment_evidence_version_id=str(uuid4()),
        assessment_sha256="a" * 64,
        assessment_kind="rule",
        assessment_period_start="2026-04-01",
        assessment_period_end="2027-03-31",
    )
    return [
        {**base, "id": purpose + "-1", "source_reference": "SYN-" + purpose + "-1"},
        {
            **base,
            "id": purpose + "-2",
            "transaction_reference": "SYN-TRANSACTION-2",
            "transaction_date": "2026-05-20",
            "amount": "80",
            "source_reference": "SYN-" + purpose + "-2",
        },
        {
            **base,
            "id": purpose + "-old",
            "source_version": "0",
            "record_status": "superseded",
            "amount": "900",
        },
    ]


def controls(**changes):
    return WithholdingObligationInput.model_validate(
        {
            "purpose": "expected",
            "legal_role": "deductor",
            "cutoff_date": "2026-06-30",
            "expected_current_rows": 2,
            "amount": "180",
            "label": "SYNTHETIC tax obligations",
            "assessment": "Independent withholding population, due dates and split cash settlement scope",
            **changes,
        }
    )


def bridge(purpose="expected", legal_role="deductor", population=None, **changes):
    return source_rows(
        {
            "table_type": "withholding-records",
            "rows": population if population is not None else records(purpose, legal_role),
        },
        controls(purpose=purpose, legal_role=legal_role, **changes),
    )


def run(population, country="IN", **changes):
    types = {
        "expected": "obligations",
        "reported": "obligations",
        "bank": "transactions",
        "allocations": "obligation-allocations",
    }
    return calculate(
        WorkflowInput.model_validate({**parameters(), **changes}),
        country,
        {
            role: {"table_type": types[role], "rows": rows, "control_totals": {}}
            for role, rows in population.items()
        },
    )


def settlement(legal_role="deductor"):
    population = example("INR")
    population["expected"] = bridge("expected", legal_role)[0]
    population["reported"] = bridge("reported", legal_role)[0]
    for index, allocation in enumerate(population["allocations"]):
        target = 0 if index == 0 else 1
        allocation["evidence_reference"] = "SYNTHETIC-TAX-CHALLAN-ADVICE"
        allocation["rationale"] = (
            "Independently assessed fictional pooled tax-challan cash allocation"
        )
        allocation.update(
            expected_id=population["expected"][target]["id"],
            reported_id=population["reported"][target]["id"],
        )
    return population


@pytest.mark.parametrize("legal_role", ["deductor", "collector"])
def test_split_and_pooled_bank_cash_keeps_transactions_and_history_separate(legal_role):
    rows, totals, current = bridge(legal_role=legal_role)
    assert totals == {"INR": "180"} and len(current) == 2
    assert rows[0]["excluded_withholding_row_ids"] == ["expected-old"]
    assert (
        rows[0]["withholding_scope"]["transaction_reference"]
        != rows[1]["withholding_scope"]["transaction_reference"]
    )
    output = run(
        settlement(legal_role),
        country="IN",
        currency="INR",
        obligation_month_start="2026-05",
        obligation_month_end="2026-05",
    )
    assert output["allocation_controls"]["allocated_amount"] == "180"
    obligations = [row for row in output["rows"] if row["kind"] == "obligation"]
    assert len(obligations) == 2 and all(row["state"] == "MATCHED" for row in obligations)
    assert len(obligations[1]["payment_allocations"]) == 2


def test_partial_payment_preserves_residual_and_does_not_claim_posted_tax_credit():
    population = settlement()
    population["allocations"] = population["allocations"][:2]
    output = run(
        population,
        country="IN",
        currency="INR",
        obligation_month_start="2026-05",
        obligation_month_end="2026-05",
    )
    assert output["allocation_controls"]["outstanding_expected"] == "30"
    assert any("PARTIALLY_SETTLED" in row.get("issues", []) for row in output["rows"])


@pytest.mark.parametrize(
    "change",
    [
        "count",
        "amount",
        "no-current",
        "ambiguous",
        "payment",
        "due",
        "assessment",
        "coverage",
        "retired",
        "role",
        "future",
    ],
)
def test_unsupported_or_uncontrolled_source_cannot_establish_obligations(change):
    population = records()
    overrides = {}
    if change == "count":
        overrides["expected_current_rows"] = 3
    elif change == "amount":
        overrides["amount"] = "1080"
    elif change == "no-current":
        population[0]["record_status"] = "cancelled"
    elif change == "ambiguous":
        population.append({**population[0], "id": "DUP", "source_reference": "DUP"})
    elif change == "payment":
        population[0]["payment_date"] = "2026-06-01"
    elif change == "due":
        population[0]["due_date"] = None
    elif change == "assessment":
        population[0]["assessment_evidence_version_id"] = None
    elif change == "coverage":
        population[0]["assessment_period_end"] = "2026-05-01"
    elif change == "retired":
        for row in population:
            row.update(legal_role="collector", tax_kind="TCS", rule_reference="206C(1H)")
        overrides["legal_role"] = "collector"
    elif change == "role":
        population[0]["legal_role"] = "deductee"
    else:
        population[0]["transaction_date"] = "2026-07-01"
    with pytest.raises(ValueError):
        bridge(population=population, **overrides)


@pytest.mark.parametrize("reference", ["206C(1H)", "TCS:206C(1H)", "tcs: 206c ( 1h )"])
@pytest.mark.parametrize(
    "transaction_date,period", [("2025-04-01", "2025-03"), ("2025-03-31", "2025-04")]
)
def test_positive_withdrawn_expectation_cannot_bypass_bank_obligation_boundary(
    reference, transaction_date, period
):
    population = [records(legal_role="collector")[0]]
    population[0].update(
        rule_reference=reference,
        transaction_date=transaction_date,
        period=period,
        tax_year_start="2025-01-01",
        tax_year_end="2025-12-31",
        assessment_period_start="2025-01-01",
        assessment_period_end="2025-12-31",
    )
    with pytest.raises(ValueError, match="withdrawn"):
        bridge(legal_role="collector", population=population, expected_current_rows=1, amount="100")


@pytest.mark.parametrize("purpose,amount", [("reported", "100"), ("expected", "0")])
def test_observed_erroneous_collection_and_zero_expectation_remain_distinct(purpose, amount):
    population = [records(purpose, "collector")[0]]
    population[0].update(rule_reference="206C(1H)", amount=amount)
    rows, totals, _ = bridge(
        purpose, "collector", population=population, expected_current_rows=1, amount=amount
    )
    assert totals == {"INR": amount}
    assert rows[0]["amount"] == amount
    assert rows[0]["withholding_scope"]["legal_role"] == "collector"


def test_historical_march_expectation_can_be_settled_later_without_new_liability():
    population = [records(legal_role="collector")[0]]
    population[0].update(
        rule_reference="TCS:206C(1H)",
        transaction_date="2025-03-31",
        period="2025-03",
        tax_year_start="2024-04-01",
        tax_year_end="2025-03-31",
        assessment_period_start="2024-04-01",
        assessment_period_end="2025-03-31",
        due_date="2025-04-07",
    )
    rows, _, _ = bridge(
        legal_role="collector", population=population, expected_current_rows=1, amount="100"
    )
    assert rows[0]["withholding_scope"]["transaction_date"] == "2025-03-31"


def test_observed_erroneous_collection_survives_zero_expected_cash_reconciliation():
    population = settlement("collector")
    for role in ("expected", "reported"):
        for row in population[role]:
            row["withholding_scope"]["rule_reference"] = "TCS:206C(1H)"
            if role == "expected":
                row["amount"] = "0"
    population["allocations"] = []
    typed_sources = {
        role: {
            "table_type": {
                "expected": "obligations",
                "reported": "obligations",
                "bank": "transactions",
                "allocations": "obligation-allocations",
            }[role],
            "rows": rows,
            "control_totals": {},
        }
        for role, rows in population.items()
    }
    typed_sources["allocations"]["nil_reason"] = (
        "Synthetic independent assessment: no bank allocation has been made"
    )
    output = calculate(
        WorkflowInput.model_validate(
            {
                **parameters(),
                "currency": "INR",
                "obligation_month_start": "2026-05",
                "obligation_month_end": "2026-05",
            }
        ),
        "IN",
        typed_sources,
    )
    rows = [r for r in output["rows"] if r["kind"] == "obligation"]
    assert all(r["expected_amount"] == "0" for r in rows)
    assert {r["reported_amount"] for r in rows} == {"100", "80"}
    assert not saved_withdrawn_expectation(output)


@pytest.mark.parametrize("scoped", [True, False])
def test_saved_cash_results_cannot_use_documented_exception_to_approve_withdrawn_positive_expectation(
    scoped,
):
    output = run(
        settlement("collector"),
        currency="INR",
        obligation_month_start="2026-05",
        obligation_month_end="2026-05",
    )
    for row in output["rows"]:
        row["auditor_status"] = "EXCEPTION_DOCUMENTED"
        if row["kind"] == "obligation":
            if scoped:
                row["withholding_scope"]["rule_reference"] = "tcs: 206c ( 1h )"
            else:
                row.pop("withholding_scope")
                row["component"] = "TCS:206C(1H)"
    retained = deepcopy(output)
    assert saved_withdrawn_expectation(output)
    assert "withdrawn period" in approval_error(output)
    assert output == retained


def test_expected_cash_source_cannot_bypass_boundary_with_canonical_scope_or_component():
    for scoped in (True, False):
        population = settlement("collector")
        for role in ("expected", "reported"):
            for row in population[role]:
                if scoped:
                    row["withholding_scope"]["rule_reference"] = "TCS:206C(1H)"
                else:
                    row.pop("withholding_scope")
                    row["component"] = " tcs: 206c ( 1h ) "
        with pytest.raises(ValueError, match="withdrawn"):
            run(
                population,
                currency="INR",
                obligation_month_start="2026-05",
                obligation_month_end="2026-05",
            )


@pytest.mark.parametrize(
    "field,value",
    [
        ("rule_reference", "DIFFERENT-SECTION"),
        ("tax_year_start", "2025-04-01"),
        ("transaction_reference", "OTHER-TX"),
        ("transaction_date", "2026-05-16"),
    ],
)
def test_cash_allocation_cannot_cross_tax_scope_even_when_amount_and_party_agree(field, value):
    population = settlement()
    population["reported"][0]["withholding_scope"][field] = value
    with pytest.raises(ValueError, match="scopes must also agree"):
        run(
            population,
            country="IN",
            currency="INR",
            obligation_month_start="2026-05",
            obligation_month_end="2026-05",
        )


def test_bank_outflow_cannot_precede_withholding_transaction():
    population = settlement()
    population["bank"][0]["date"] = "2026-05-01"
    with pytest.raises(ValueError, match="predates withholding"):
        run(
            population,
            country="IN",
            currency="INR",
            settlement_start="2026-05-01",
            obligation_month_start="2026-05",
            obligation_month_end="2026-05",
        )


def test_cross_country_and_invalid_scope_component_rejected():
    with pytest.raises(ValueError, match="Indian domestic"):
        run(
            settlement(),
            country="AE",
            currency="INR",
            obligation_month_start="2026-05",
            obligation_month_end="2026-05",
        )
    row = bridge()[0][0]
    canonical = {field: row[field] for field in Obligation.model_fields if field in row}
    canonical["component"] = "PF:EMPLOYEE"
    with pytest.raises(ValueError, match="exact TDS/TCS"):
        Obligation.model_validate(canonical)


def test_non_current_observation_selection_remains_visible_and_not_aggregated():
    rows, _, _ = bridge()
    assert sum(len(row["excluded_withholding_row_ids"]) for row in rows) == 1
    assert [row["amount"] for row in rows] == ["100", "80"]
    other = deepcopy(records())
    for row in other:
        row.update(assessment_evidence_version_id=None, assessment_kind=None)
    assert bridge("reported", population=other)[1] == {"INR": "180"}
