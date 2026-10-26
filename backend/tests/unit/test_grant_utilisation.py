import uuid
from datetime import date
from types import SimpleNamespace as NS

import pytest
from pydantic import ValidationError

from app.modules.country_workflows.grant_utilisation import (
    ROW_TYPES,
    GrantBudget,
    GrantControl,
    compare,
)


def packet(country="AE"):
    currency = "AED" if country == "AE" else "INR"
    tables = dict(
        budgets=[
            dict(
                id="B1",
                fund_id="F1",
                category="training",
                donor="D1",
                project="P1",
                country=country,
                currency=currency,
                valid_from="2025-01-01",
                valid_to="2027-12-31",
                category_ceiling="1000",
                fund_ceiling="1500",
                mandate_reference="SYNTHETIC mandate appendix",
                source_evidence_version_id=str(uuid.uuid4()),
                source_sha256="a" * 64,
                assessment="Synthetic professionally assessed grant terms",
            )
        ],
        expenses=[
            dict(
                id="E1",
                account="5000",
                project="P1",
                vendor="V1",
                reference="SYN-INV-1",
                line_reference="LINE-1",
                currency=currency,
                date="2026-06-30",
                kind="expense",
                amount="300",
                evidence_reference="SYN-COST-1",
            )
        ],
        allocations=[
            dict(
                id="A1",
                expense_id="E1",
                fund_id="F1",
                category="training",
                currency=currency,
                amount="300",
                rationale="Synthetic project expenditure allocation",
            )
        ],
        controls=[
            dict(
                id="C1",
                kind="expense-period",
                account="5000",
                currency=currency,
                period_start="2026-01-01",
                period_end="2026-12-31",
                amount="300",
                expected_rows=1,
                positive_amount="300",
                negative_amount="0",
                ledger_reference="SYN-LEDGER-1",
                assessment="Independent synthetic expense ledger controls",
            ),
            dict(
                id="O1",
                kind="fund-opening",
                fund_id="F1",
                category="training",
                currency=currency,
                period_start="2025-12-31",
                period_end="2025-12-31",
                amount="200",
                ledger_reference="SYN-OPENING-1",
                assessment="Independent synthetic opening utilisation",
            ),
        ],
    )
    for role, kind in dict(
        budgets="grant-budgets",
        expenses="grant-expenses",
        allocations="grant-allocations",
        controls="grant-utilisation-controls",
    ).items():
        tables[role] = [
            ROW_TYPES[kind].model_validate(row).model_dump(mode="json") for row in tables[role]
        ]
    return tables


def run(tables=None, country="AE"):
    return compare(
        NS(period_start=date(2026, 1, 1), as_of=date(2026, 12, 31)),
        tables or packet(country),
        country,
    )


def kind(result, value):
    return [row for row in result["rows"] if row["kind"] == value]


@pytest.mark.parametrize("country", ["AE", "IN"])
def test_expense_control_opening_and_mandate_are_separate(country):
    result = run(country=country)
    assert not result["blocked"] and result["exception_count"] == 0
    category = kind(result, "category-budget")[0]
    assert category["opening_amount"] == "200"
    assert category["closing_utilisation"] == "500"
    assert category["remaining_under_signed_schedule"] == "500"
    assert kind(result, "fund-budget")[0]["remaining_under_signed_schedule"] == "1000"
    assert result["cash_availability_established"] is False
    assert result["certificate_issued"] is False


def test_two_funds_cannot_charge_the_same_expense_twice():
    tables = packet()
    tables["allocations"].append(dict(tables["allocations"][0], id="A2", fund_id="F2"))
    result = run(tables)
    assert result["blocked"]
    assert kind(result, "expense-allocation-control")[0]["difference"] == "-300"
    assert "MISSING_CATEGORY_MANDATE" in kind(result, "allocation")[1]["reasons"]


def test_multiple_categories_must_respect_the_whole_fund_ceiling():
    tables = packet()
    tables["budgets"].append(dict(tables["budgets"][0], id="B2", category="equipment"))
    tables["controls"].append(
        dict(tables["controls"][1], id="O2", category="equipment", amount="700")
    )
    tables["controls"][1]["amount"] = "700"
    result = run(tables)
    assert "FUND_BUDGET_EXCEEDED" in kind(result, "fund-budget")[0]["reasons"]
    assert not result["blocked"]  # Supported finding, not an invented certificate.


@pytest.mark.parametrize(
    "field,value",
    [
        ("amount", "299"),
        ("expected_rows", 2),
        ("positive_amount", "301"),
        ("negative_amount", "-1"),
    ],
)
def test_net_and_gross_counts_are_independent_controls(field, value):
    tables = packet()
    tables["controls"][0][field] = value
    assert run(tables)["blocked"]


def test_missing_opening_is_not_zero():
    tables = packet()
    tables["controls"].pop()
    result = run(tables)
    assert result["blocked"]
    assert kind(result, "category-budget")[0]["opening_amount"] is None
    assert kind(result, "fund-budget")[0]["closing_utilisation"] is None


def test_unknown_category_does_not_escape_fund_consumption():
    tables = packet()
    tables["allocations"][0]["category"] = "unassessed"
    result = run(tables)
    assert result["blocked"]
    assert kind(result, "fund-budget")[0]["closing_utilisation"] == "500"


@pytest.mark.parametrize(
    "field,value,reason",
    [("currency", "USD", "CURRENCY_MISMATCH"), ("project", "P2", "PROJECT_MISMATCH")],
)
def test_expense_scope_mismatch_never_auto_matches(field, value, reason):
    tables = packet()
    tables["expenses"][0][field] = value
    result = run(tables)
    assert result["blocked"] and reason in kind(result, "allocation")[0]["reasons"]


def test_expired_mandate_is_a_review_finding_not_ignored_spend():
    tables = packet()
    tables["budgets"][0]["valid_to"] = "2026-05-31"
    result = run(tables)
    assert "OUTSIDE_MANDATE_DATES" in kind(result, "allocation")[0]["reasons"]
    assert kind(result, "category-budget")[0]["closing_utilisation"] == "500"


def test_credit_preserves_gross_amounts_and_always_requires_recovery_review():
    tables = packet()
    expense = dict(
        tables["expenses"][0],
        id="CR1",
        reference="SYN-CREDIT-1",
        kind="credit",
        amount="-50",
        original_reference="SYN-INV-1",
    )
    tables["expenses"].append(expense)
    allocation = dict(
        tables["allocations"][0],
        id="CA1",
        expense_id="CR1",
        amount="-50",
        credit_original_reference="SYN-INV-1",
        credit_evidence_version_id=str(uuid.uuid4()),
        credit_source_sha256="b" * 64,
    )
    tables["allocations"].append(allocation)
    tables["controls"][0].update(
        amount="250", positive_amount="300", negative_amount="-50", expected_rows=2
    )
    result = run(tables)
    assert not result["blocked"]
    row = kind(result, "category-budget")[0]
    assert (row["positive_amount"], row["negative_amount"], row["closing_utilisation"]) == (
        "300",
        "-50",
        "450",
    )
    assert "CREDIT_RECOVERY_REVIEW" in row["reasons"]
    del allocation["credit_evidence_version_id"]
    with pytest.raises(ValidationError):
        ROW_TYPES["grant-allocations"].model_validate(allocation)


def test_country_and_duplicate_mandate_fail_closed():
    with pytest.raises(ValueError, match="country"):
        run(packet("IN"))
    tables = packet()
    tables["budgets"].append(dict(tables["budgets"][0], id="B2"))
    with pytest.raises(ValueError, match="Ambiguous"):
        run(tables)


def test_duplicate_original_voucher_line_cannot_be_renamed():
    tables = packet()
    tables["expenses"].append(dict(tables["expenses"][0], id="E2"))
    with pytest.raises(ValueError, match="voucher"):
        run(tables)


def test_control_type_scope_and_totals_reject_ambiguous_declarations():
    control = packet()["controls"][0]
    for changes in (
        dict(expected_rows=True),
        dict(fund_id="F1"),
        dict(negative_amount=None),
        dict(amount="301"),
    ):
        with pytest.raises(ValidationError):
            GrantControl.model_validate({**control, **changes})
    with pytest.raises(ValidationError):
        GrantBudget.model_validate(dict(packet()["budgets"][0], valid_to="2024-01-01"))


def test_nil_expense_population_still_needs_an_explicit_independent_account_control():
    tables = packet()
    tables["expenses"] = []
    tables["allocations"] = []
    tables["controls"][0].update(
        amount="0", expected_rows=0, positive_amount="0", negative_amount="0"
    )
    assert run(tables)["exception_count"] == 0
    tables["controls"].pop(0)
    with pytest.raises(ValueError, match="explicit expense account control"):
        run(tables)


def test_result_id_namespaces_and_decimal_precision():
    tables = packet()
    tables["allocations"][0]["id"] = "expense:E1"
    for role in ("expenses", "allocations"):
        tables[role][0]["amount"] = "12345678901234567890.12345678"
    tables["controls"][0].update(
        amount="12345678901234567890.12345678", positive_amount="12345678901234567890.12345678"
    )
    result = run(tables)
    assert len({row["id"] for row in result["rows"]}) == len(result["rows"])
    assert (
        kind(result, "category-budget")[0]["closing_utilisation"] == "12345678901234568090.12345678"
    )


@pytest.mark.parametrize("when", ["2025-12-31", "2027-01-01"])
def test_out_of_window_expenses_are_never_silently_filtered(when):
    tables = packet()
    tables["expenses"][0]["date"] = when
    with pytest.raises(ValueError, match="no silent filtering"):
        run(tables)


def test_valid_cost_split_uses_one_shared_expense_capacity():
    tables = packet()
    tables["budgets"].append(dict(tables["budgets"][0], id="B2", fund_id="F2"))
    tables["controls"].append(dict(tables["controls"][1], id="O2", fund_id="F2", amount="0"))
    tables["allocations"][0]["amount"] = "100"
    tables["allocations"].append(
        dict(tables["allocations"][0], id="A2", fund_id="F2", amount="200")
    )
    result = run(tables)
    assert not result["blocked"] and result["exception_count"] == 0
    assert [row["closing_utilisation"] for row in kind(result, "fund-budget")] == ["300", "200"]


def test_negative_opening_is_visible_even_when_new_costs_make_the_balance_positive():
    tables = packet()
    tables["controls"][1]["amount"] = "-100"
    result = run(tables)
    assert "NEGATIVE_OPENING_UTILISATION_REVIEW" in kind(result, "category-budget")[0]["reasons"]
    assert "NEGATIVE_OPENING_UTILISATION_REVIEW" in kind(result, "fund-budget")[0]["reasons"]


def test_budget_zero_is_real_and_a_small_excess_is_not_tolerated():
    tables = packet()
    tables["budgets"][0]["category_ceiling"] = "0"
    row = kind(run(tables), "category-budget")[0]
    assert row["ceiling"] == "0" and "CATEGORY_BUDGET_EXCEEDED" in row["reasons"]


def test_five_thousand_expenses_retain_all_allocation_and_control_rows():
    tables = packet()
    template_expense = tables["expenses"][0]
    template_allocation = tables["allocations"][0]
    tables["expenses"] = [
        dict(template_expense, id=f"E-{i:04d}", reference=f"SYN-INV-{i:04d}", amount="1")
        for i in range(5000)
    ]
    tables["allocations"] = [
        dict(template_allocation, id=f"A-{i:04d}", expense_id=f"E-{i:04d}", amount="1")
        for i in range(5000)
    ]
    tables["controls"][0].update(amount="5000", positive_amount="5000", expected_rows=5000)
    tables["budgets"][0].update(category_ceiling="10000", fund_ceiling="15000")
    result = run(tables)
    assert not result["blocked"] and result["exception_count"] == 0
    assert len(result["rows"]) == 10003
    assert kind(result, "expense-allocation-control")[-1]["expense_id"] == "E-4999"
    assert kind(result, "fund-budget")[0]["closing_utilisation"] == "5200"


def test_canonical_csv_preserves_independent_controls_and_rejects_trimmed_identifiers():
    import csv
    import io

    from app.modules.country_workflows.schemas import SourceInput
    from app.modules.country_workflows.sources import parse_csv

    tables = packet()
    for role, table_type, total in (
        ("budgets", "grant-budgets", "1000"),
        ("expenses", "grant-expenses", "300"),
        ("allocations", "grant-allocations", "300"),
        ("controls", "grant-utilisation-controls", "500"),
    ):
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=list(tables[role][0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(tables[role])
        data = SourceInput(
            evidence_version_id=uuid.uuid4(),
            table_type=table_type,
            label="SYNTHETIC grant source",
            expected_rows=len(tables[role]),
            control_totals={"AED": total},
        )
        parsed = parse_csv(output.getvalue().encode(), data)
        assert parsed["row_count"] == len(tables[role])
        assert parsed["control_totals"] == {"AED": total}
        if role == "expenses":
            with pytest.raises(ValueError, match="trimmed"):
                parse_csv(output.getvalue().replace("SYN-INV-1", " SYN-INV-1").encode(), data)


def test_pure_calculation_cannot_pass_retained_document_approval_gate():
    from app.modules.country_workflows.review import approval_error

    result = {**run(), "workflow": "grant-utilisation"}
    assert "retained" in approval_error(result)


@pytest.mark.parametrize(
    "role,table_type,field",
    [
        ("budgets", "grant-budgets", "valid_from"),
        ("expenses", "grant-expenses", "date"),
        ("controls", "grant-utilisation-controls", "period_start"),
    ],
)
def test_canonical_grant_dates_do_not_infer_midnight_timestamps(role, table_type, field):
    row = packet()[role][0]
    row[field] += "T00:00:00Z"
    with pytest.raises(ValidationError, match="calendar"):
        ROW_TYPES[table_type].model_validate(row)


@pytest.mark.parametrize(
    "change", [{"as_of": "2026-12-31T00:00:00Z"}, {"date_tolerance": 1}, {"tolerance": "0.01"}]
)
def test_grant_request_rejects_implicit_dates_and_fuzzy_controls(change):
    from app.modules.country_workflows.schemas import WorkflowInput

    values = dict(
        workflow="grant-utilisation",
        source_ids={
            key: uuid.uuid4() for key in ("budgets", "expenses", "allocations", "controls")
        },
        period_start="2026-01-01",
        as_of="2026-12-31",
        title="SYNTHETIC grant",
        rationale="Controlled synthetic accounting review",
    )
    with pytest.raises(ValidationError):
        WorkflowInput.model_validate({**values, **change})


def test_multiple_currencies_never_net_fund_limits():
    tables = packet()
    second = packet()
    for role, population in second.items():
        for row in population:
            row["id"] += "-USD"
            row["currency"] = "USD"
            if "fund_id" in row and row["fund_id"]:
                row["fund_id"] = "F2"
            if "expense_id" in row:
                row["expense_id"] += "-USD"
        tables[role].extend(population)
    result = run(tables)
    assert not result["blocked"]
    assert result["currency_scope"] == ["AED", "USD"]
    assert {
        (row["currency"], row["closing_utilisation"]) for row in kind(result, "fund-budget")
    } == {("AED", "500"), ("USD", "500")}


def test_equivalent_numeric_fund_ceilings_do_not_create_an_ambiguity():
    tables = packet()
    tables["budgets"].append(
        dict(tables["budgets"][0], id="B2", category="equipment", fund_ceiling="1500.00")
    )
    tables["controls"].append(
        dict(tables["controls"][1], id="O2", category="equipment", amount="0")
    )
    assert run(tables)["exception_count"] == 0


def test_complete_grant_workbook_does_not_truncate_ten_thousand_result_links():
    import io

    from openpyxl import load_workbook

    from app.modules.intelligence.exports import render

    tables = packet()
    expense = tables["expenses"][0]
    allocation = tables["allocations"][0]
    tables["expenses"] = [
        dict(expense, id=f"E-{i:04d}", reference=f"SYN-INV-{i:04d}", amount="1")
        for i in range(5000)
    ]
    tables["allocations"] = [
        dict(allocation, id=f"A-{i:04d}", expense_id=f"E-{i:04d}", amount="1") for i in range(5000)
    ]
    tables["controls"][0].update(amount="5000", positive_amount="5000", expected_rows=5000)
    tables["budgets"][0].update(category_ceiling="10000", fund_ceiling="15000")
    body = {**run(tables), "workflow": "grant-utilisation"}
    content, _ = render(
        dict(
            id=str(uuid.uuid4()),
            version=1,
            sha256="a" * 64,
            created_at="2026-06-30T00:00:00Z",
            kind="country-workflow",
            body=body,
            dependencies=[],
        ),
        "xlsx",
    )
    book = load_workbook(io.BytesIO(content), read_only=True)
    records = list(book["Rows"].values)
    assert len(records) == 10004
    header = records[0]
    assert sum(row[header.index("expense_id")] == "E-4999" for row in records[1:]) == 2


@pytest.mark.parametrize("value", ["ID\x07", "ID\x7f", "ID\uffff"])
def test_grant_text_rejects_nonrepresentable_identifiers_before_export(value):
    with pytest.raises(ValidationError):
        GrantBudget.model_validate(dict(packet()["budgets"][0], fund_id=value))


@pytest.mark.parametrize("country", ["AE", "IN"])
@pytest.mark.parametrize("case", ["matched", "credit", "nil", "over-budget"])
def test_saved_grant_examples_preserve_files_controls_and_expected_outcomes(country, case):
    import hashlib
    import json
    from pathlib import Path

    from app.modules.country_workflows.grant_utilisation import ROLES
    from app.modules.country_workflows.schemas import SourceInput
    from app.modules.country_workflows.sources import parse_csv

    folder = (
        Path(__file__).resolve().parents[3]
        / "docs/country-workflows/sample-inputs/SYNTHETIC-grant-utilisation"
        / country
        / case
    )
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    for name, digest in manifest["sha256"].items():
        assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == digest
    tables = {}
    for role in ROLES:
        controls = manifest["source_controls"][role]
        options = SourceInput(
            evidence_version_id=uuid.uuid4(), label="SYNTHETIC saved grant source", **controls
        )
        parsed = parse_csv(
            (folder / (role + ".csv")).read_bytes(),
            options,
            manifest["budget_binding_defaults"] if role == "budgets" else None,
        )
        tables[role] = parsed["rows"]
    result = compare(
        NS(
            period_start=date.fromisoformat(manifest["period_start"]),
            as_of=date.fromisoformat(manifest["as_of"]),
        ),
        tables,
        country,
    )
    expected = manifest["expected"]
    assert result["exception_count"] == expected["exception_count"]
    assert result["blocked"] == expected["blocked"]
    assert (
        kind(result, "category-budget")[0]["closing_utilisation"] == expected["closing_utilisation"]
    )
