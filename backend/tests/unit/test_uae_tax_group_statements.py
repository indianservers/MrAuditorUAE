"""Synthetic, independently specified arithmetic controls; no client qualification."""

from copy import deepcopy
from uuid import uuid4

import pytest

from app.modules.ifrs.uae_tax_group_statements import CONTRACT, TaxGroupStatements, calculate


def line(reference, statement, kind, amount, **extra):
    return {
        "reference": reference,
        "statement": statement,
        "code": reference,
        "label": reference,
        "kind": kind,
        "amount": str(amount),
        "treatment": "ordinary",
        "source_reference": "SYNTHETIC independently mapped source row",
        **extra,
    }


def member(name, role, cash, equity, income, expense, opening, **extra):
    profit = income + expense
    return {
        "member": name,
        "legal_entity_id": str(uuid4()),
        "role": role,
        "period_start": "2025-01-01",
        "period_end": "2025-12-31",
        "membership_from": "2025-01-01",
        "membership_through": "2025-12-31",
        "currency": "AED",
        "basis": "standalone_unconsolidated",
        "accounting_standard": "IFRS",
        "uniform_policy": "assessed_aligned",
        "policy_assessment": "SYNTHETIC explicitly aligned accounting policies",
        "source_evidence_version_id": str(uuid4()),
        "source_sha256": "a" * 64,
        "lines": [
            line("cash", "position", "asset", cash),
            line("payable", "position", "liability", 0),
            line("equity", "position", "equity", -equity),
            line("sales", "profit_loss", "income", income),
            line("expenses", "profit_loss", "expense", expense),
            line("oci", "oci", "oci", 0),
            line("opening-equity", "changes_equity", "opening_equity", opening),
            line("profit-transfer", "changes_equity", "profit", profit),
            line("oci-transfer", "changes_equity", "oci", 0),
            line("closing-equity", "changes_equity", "closing_equity", equity),
        ],
        **extra,
    }


def sample():
    parent = member("A", "parent", 100, 150, 100, -60, 110)
    parent["lines"].append(
        line(
            "investment",
            "position",
            "asset",
            50,
            treatment="member_investment",
            counterparty_member="B",
            transaction_reference="INV-B",
        )
    )
    subsidiary = member("B", "subsidiary", 70, 70, 80, -50, 40)
    subsidiary["lines"][2].update(
        treatment="member_equity", counterparty_member="A", transaction_reference="INV-B"
    )
    return {
        "contract": CONTRACT,
        "group_reference": "SYNTHETIC-GROUP",
        "first_group_period_start": "2025-01-01",
        "comparative": None,
        "comparative_basis": "first_group_period",
        "current": {
            "period_start": "2025-01-01",
            "period_end": "2025-12-31",
            "population": "assessed_complete",
            "intramember_population": "assessed_complete",
            "population_assessment": "SYNTHETIC complete independently declared member and transaction population",
            "members": [parent, subsidiary],
            "adjustments": [],
            "pre_join_losses": [],
            "basis_of_preparation": "SYNTHETIC basis text awaiting exact authority wording and independent review",
            "accounting_policies": "SYNTHETIC common policies awaiting source binding",
            "estimates_and_judgments": "SYNTHETIC estimates and judgments awaiting source binding",
            "membership_disclosures": "SYNTHETIC parent and subsidiary facts awaiting independent review",
        },
    }


def result(data=None):
    return calculate(TaxGroupStatements.model_validate(data or sample()))


def adjustment(reference, member_id, target, delta, category, **extra):
    return {
        "reference": reference,
        "member": member_id,
        "line_reference": target,
        "delta": str(delta),
        "category": category,
        "rationale": "SYNTHETIC independently prepared explicit adjustment",
        "source_reference": "SYNTHETIC source adjustment schedule",
        **extra,
    }


def test_four_statements_preserve_gross_investments_equity_and_all_source_rows():
    actual = result()
    current = actual["current"]
    assert current["totals"] == {
        "assets": "220",
        "liabilities": "0",
        "equity": "220",
        "profit_loss_sum": "70",
        "profit_before_uae_corporate_tax": "70",
        "oci": "0",
        "opening_equity": "150",
        "closing_equity": "220",
    }
    assert actual["issues"] == []
    assert current["arithmetic_reconciled"]
    assert set(current["statements"]) == {"position", "profit_loss", "oci", "changes_equity"}
    investment = next(r for r in current["statements"]["position"] if r["code"] == "investment")
    assert investment["amount"] == "50"
    assert investment["source_lines"][0]["original_amount"] == "50"
    assert investment["source_lines"][0]["adjustment"] == "0"
    assert actual["validation"]["ready"] is False
    assert actual["source_binding_established"] is False
    assert actual["statutory_issuance"] is False


def test_equal_opposite_member_source_errors_cannot_hide_in_a_balanced_group():
    data = sample()
    data["current"]["members"][0]["lines"][0]["amount"] = "110"
    data["current"]["members"][1]["lines"][0]["amount"] = "60"
    actual = result(data)
    assert actual["current"]["reconciliation_differences"]["position_balance"] == "0"
    assert not actual["current"]["arithmetic_reconciled"]
    assert {
        i["member"] for i in actual["issues"] if i["code"] == "SOURCE_MEMBER_POSITION_BALANCE"
    } == {"A", "B"}


def test_explicit_tax_exclusion_keeps_the_retained_equity_bridge_and_never_invents_a_journal():
    data = sample()
    a = data["current"]["members"][0]
    a["lines"][4]["treatment"] = "uae_ct_current"
    a["lines"].append(line("tax-equity-bridge", "changes_equity", "other", 0))
    assert result(data)["current"]["totals"]["profit_before_uae_corporate_tax"] is None
    data["current"]["adjustments"] = [
        adjustment("TAX-EXPENSE", "A", "expenses", 60, "uae_ct_exclusion"),
        adjustment("TAX-PROFIT", "A", "profit-transfer", 60, "uae_ct_exclusion"),
        adjustment("TAX-EQUITY", "A", "tax-equity-bridge", -60, "uae_ct_exclusion"),
    ]
    original = deepcopy(data)
    actual = result(data)
    assert actual["current"]["totals"]["profit_before_uae_corporate_tax"] == "130"
    assert actual["current"]["totals"]["closing_equity"] == "220"
    assert actual["current"]["arithmetic_reconciled"]
    assert not actual["issues"]
    assert actual["statutory_issuance"] is False
    assert data == original


@pytest.mark.parametrize("field", ["amount", "delta"])
@pytest.mark.parametrize("value", [True, 0.1, float("inf"), float("nan")])
def test_binary_and_boolean_amounts_fail_closed(field, value):
    data = sample()
    if field == "amount":
        data["current"]["members"][0]["lines"][0][field] = value
    else:
        data["current"]["adjustments"] = [adjustment("SYN-ADJ", "A", "cash", "1", "uniform_policy")]
        data["current"]["adjustments"][0][field] = value
    with pytest.raises(ValueError, match="exact decimal"):
        result(data)


def test_long_exact_amounts_are_neither_rounded_nor_accumulated_at_default_decimal_precision():
    data = sample()
    a = data["current"]["members"][0]
    a["lines"][0]["amount"] = "99999999999999999899.12345678"
    a["lines"][2]["amount"] = "-99999999999999999949.12345678"
    a["lines"][6]["amount"] = "99999999999999999909.12345678"
    a["lines"][9]["amount"] = "99999999999999999949.12345678"
    actual = result(data)
    assert actual["current"]["totals"]["assets"] == "100000000000000000019.12345678"
    assert actual["current"]["arithmetic_reconciled"]


@pytest.mark.parametrize("amount", ["0E-1000000000", "1e3", "0." + "0" * 100, " " * 100])
def test_exponent_or_unbounded_decimal_text_is_rejected_before_serialization(amount):
    data = sample()
    data["current"]["members"][0]["lines"][0]["amount"] = amount
    with pytest.raises(ValueError, match="bounded plain decimal"):
        result(data)


def test_explicit_reciprocal_elimination_does_not_eliminate_investments():
    data = sample()
    a, b = data["current"]["members"]
    a["lines"][0]["amount"] = "80"
    a["lines"].append(
        line("loan", "position", "asset", 20, counterparty_member="B", transaction_reference="LOAN")
    )
    b["lines"][0]["amount"] = "90"
    b["lines"][1].update(amount="-20", counterparty_member="A", transaction_reference="LOAN")
    assert "INTRAMEMBER_AMOUNT_REMAINS" in {i["code"] for i in result(data)["issues"]}
    data["current"]["adjustments"] = [
        adjustment(
            "A-LOAN",
            "A",
            "loan",
            -20,
            "intramember_elimination",
            counterparty_member="B",
            transaction_reference="LOAN",
        ),
        adjustment(
            "B-LOAN",
            "B",
            "payable",
            20,
            "intramember_elimination",
            counterparty_member="A",
            transaction_reference="LOAN",
        ),
    ]
    actual = result(data)
    assert not actual["issues"]
    assert actual["current"]["totals"]["assets"] == "220"
    assert (
        next(r for r in actual["current"]["statements"]["position"] if r["code"] == "investment")[
            "amount"
        ]
        == "50"
    )
    assert len(actual["current"]["adjustments"]) == 2


@pytest.mark.parametrize(
    "target,member_id,counterparty", [("investment", "A", "B"), ("equity", "B", "A")]
)
def test_ifrs10_investment_or_equity_elimination_is_rejected(target, member_id, counterparty):
    data = sample()
    data["current"]["adjustments"] = [
        adjustment(
            "IFRS10",
            member_id,
            target,
            -1,
            "intramember_elimination",
            counterparty_member=counterparty,
            transaction_reference="INV-B",
        )
    ]
    with pytest.raises(ValueError, match="Do not eliminate"):
        result(data)


def test_direct_member_investment_impairment_is_not_silently_eliminated():
    data = sample()
    data["current"]["members"][0]["lines"][4].update(
        treatment="direct_member_investment_impairment",
        counterparty_member="B",
        transaction_reference="IMP-B",
    )
    assert "INTRAMEMBER_AMOUNT_REMAINS" not in {i["code"] for i in result(data)["issues"]}
    data["current"]["adjustments"] = [
        adjustment(
            "IMP-ELIM",
            "A",
            "expenses",
            60,
            "intramember_elimination",
            counterparty_member="B",
            transaction_reference="IMP-B",
        )
    ]
    with pytest.raises(ValueError, match="direct investment impairment"):
        result(data)


@pytest.mark.parametrize(
    "treatment", ["uae_ct_current", "uae_ct_deferred", "consolidation_only_acquisition"]
)
def test_framework_exclusions_remain_blocking_until_explicitly_adjusted(treatment):
    data = sample()
    data["current"]["members"][0]["lines"][4]["treatment"] = treatment
    assert "FRAMEWORK_EXCLUSION_REMAINS" in {i["code"] for i in result(data)["issues"]}


def test_foreign_emirate_tax_is_retained_and_cannot_be_excluded_as_uae_ct():
    data = sample()
    data["current"]["members"][0]["lines"][4]["treatment"] = "foreign_or_emirate_tax"
    assert result(data)["current"]["totals"]["profit_before_uae_corporate_tax"] == "70"
    data["current"]["adjustments"] = [
        adjustment("WRONG-TAX", "A", "expenses", 60, "uae_ct_exclusion")
    ]
    with pytest.raises(ValueError, match="Foreign and emirate"):
        result(data)


def test_standalone_business_acquisition_is_not_separate_entity_consolidation_goodwill():
    data = sample()
    data["current"]["members"][0]["lines"][0]["treatment"] = "standalone_business_acquisition"
    assert not result(data)["issues"]
    data["current"]["adjustments"] = [
        adjustment("WRONG-GW", "A", "cash", -100, "consolidation_acquisition_removal")
    ]
    with pytest.raises(ValueError, match="standalone business-acquisition"):
        result(data)


@pytest.mark.parametrize(
    "changes,unresolved",
    [
        ({}, True),
        (
            {
                "measurement_basis": "cost_less_impairment",
                "cost_basis": "110",
                "cumulative_impairment": "10",
            },
            False,
        ),
        (
            {
                "measurement_basis": "cost_less_impairment",
                "cost_basis": "100",
                "cumulative_impairment": "10",
            },
            True,
        ),
        ({"measurement_basis": "other", "cost_basis": "110", "cumulative_impairment": "10"}, True),
    ],
)
def test_nonmember_investment_requires_an_explicit_cost_less_impairment_bridge(changes, unresolved):
    data = sample()
    data["current"]["members"][0]["lines"][0].update(treatment="nonmember_investment", **changes)
    actual = result(data)
    assert (
        "NONMEMBER_INVESTMENT_COST_BRIDGE_UNRESOLVED" in {i["code"] for i in actual["issues"]}
    ) is unresolved
    assert actual["current"]["totals"]["assets"] == "220"


@pytest.mark.parametrize(
    "changes",
    [
        {"counterparty_member": "B", "transaction_reference": "OUTSIDE-INV"},
        {"cost_basis": "10", "cumulative_impairment": "11"},
    ],
)
def test_nonmember_investments_cannot_be_treated_as_members_or_exceed_their_cost(changes):
    data = sample()
    data["current"]["members"][0]["lines"][0].update(treatment="nonmember_investment", **changes)
    with pytest.raises(ValueError):
        result(data)


@pytest.mark.parametrize("field", ["population", "intramember_population"])
def test_unassessed_complete_populations_are_not_cleared_by_balanced_numbers(field):
    data = sample()
    data["current"][field] = "unassessed"
    actual = result(data)
    assert actual["current"]["arithmetic_reconciled"]
    assert {"period": "current", "code": "POPULATION_UNASSESSED", "scope": field} in actual[
        "issues"
    ]
    assert not actual["validation"]["framework_inputs_without_detected_issues"]


@pytest.mark.parametrize(
    "line_index,code",
    [
        (0, "POSITION_BALANCE"),
        (3, "PROFIT_TRANSFER_AGREEMENT"),
        (5, "OCI_TRANSFER_AGREEMENT"),
        (6, "EQUITY_ROLLFORWARD"),
        (9, "EQUITY_POSITION_AGREEMENT"),
    ],
)
def test_each_cross_statement_reconciliation_detects_independent_errors(line_index, code):
    data = sample()
    data["current"]["members"][0]["lines"][line_index]["amount"] = "999"
    actual = result(data)
    assert code in {i["code"] for i in actual["issues"]}
    assert not actual["current"]["arithmetic_reconciled"]


def existing_group():
    data = sample()
    data["first_group_period_start"] = "2024-01-01"
    data["comparative_basis"] = "assessed_current_framework"
    prior = deepcopy(data["current"])
    prior.update(period_start="2024-01-01", period_end="2024-12-31")
    for m in prior["members"]:
        m.update(
            period_start="2024-01-01",
            period_end="2024-12-31",
            membership_from="2024-01-01",
            membership_through="2024-12-31",
        )
    data["comparative"] = prior
    return data


def test_first_framework_year_does_not_create_first_group_period_exemption():
    data = existing_group()
    assert result(data)["comparative"]["totals"]["equity"] == "220"
    data["comparative"] = None
    with pytest.raises(ValueError, match="existing group requires"):
        result(data)


def test_comparatives_retain_prior_only_lines_and_do_not_invent_zero_prior_figures():
    data = existing_group()
    data["comparative"]["members"][0]["lines"][0]["code"] = "PRIOR-ONLY-CASH"
    actual = result(data)
    assert (
        next(
            r
            for r in actual["comparative"]["statements"]["position"]
            if r["code"] == "PRIOR-ONLY-CASH"
        )["amount"]
        == "100"
    )
    assert not any(
        r["code"] == "PRIOR-ONLY-CASH" for r in actual["current"]["statements"]["position"]
    )
    assert actual["comparative"]["notes"] == actual["current"]["notes"]


def test_changed_prior_membership_is_retained_as_its_own_population_not_rewritten():
    data = existing_group()
    data["comparative"]["members"][1]["legal_entity_id"] = str(uuid4())
    actual = result(data)
    source = actual["comparative"]["statements"]["position"][0]["source_lines"][1]
    assert source["member"] == "B"
    assert (
        actual["comparative"]["members"][1]["legal_entity_id"]
        != actual["current"]["members"][1]["legal_entity_id"]
    )
    assert actual["validation"]["ready"] is False


def test_unassessed_comparative_framework_is_flagged_even_when_arithmetic_matches():
    data = existing_group()
    data["comparative_basis"] = "unassessed"
    assert {"code": "COMPARATIVE_FRAMEWORK_BASIS_UNASSESSED"} in result(data)["issues"]


def test_prejoin_deductible_loss_prevents_premature_elimination_and_exposes_income_ceiling():
    data = sample()
    data["current"]["pre_join_losses"] = [
        {
            "transaction_reference": "PREJOIN",
            "members": ["A", "B"],
            "deductible_loss": "100",
            "previously_reversed": "30",
            "period_income": "20",
            "source_reference": "SYNTHETIC prejoin deduction and reversals",
            "assessment": "SYNTHETIC independently assessed loss reversal history",
        }
    ]
    data["current"]["members"][0]["lines"][3].update(
        counterparty_member="B", transaction_reference="PREJOIN"
    )
    actual = result(data)
    schedule = actual["current"]["pre_join_loss_schedule"][0]
    assert schedule["unreversed_before_period"] == "70"
    assert schedule["period_income_ceiling_for_tax_review"] == "20"
    assert schedule["unreversed_after_declared_income"] == "50"
    assert "PRE_JOIN_LOSS_ACCOUNTING_AND_TAX_BRIDGE_REQUIRES_REVIEW" in {
        i["code"] for i in actual["issues"]
    }
    data["current"]["adjustments"] = [
        adjustment(
            "PREMATURE",
            "A",
            "sales",
            -100,
            "intramember_elimination",
            counterparty_member="B",
            transaction_reference="PREJOIN",
        )
    ]
    with pytest.raises(ValueError, match="pre-join deductible loss remains"):
        result(data)


@pytest.mark.parametrize(
    "fault",
    [
        "nonmember",
        "self",
        "chart",
        "missing-target",
        "missing-oci",
        "missing-opening",
        "duplicate-entity",
        "different-year",
        "consolidated",
        "currency",
        "partial-membership",
        "missing-counterparty",
        "source-precision",
        "blank-notes",
    ],
)
def test_inconsistent_scope_and_mapping_fail_closed(fault):
    data = sample()
    a, b = data["current"]["members"]
    if fault == "nonmember":
        a["lines"][-1]["counterparty_member"] = "OUTSIDE"
    elif fault == "self":
        a["lines"][-1]["counterparty_member"] = "A"
    elif fault == "chart":
        b["lines"][0]["kind"] = "liability"
    elif fault == "missing-target":
        data["current"]["adjustments"] = [adjustment("MISSING", "A", "absent", 1, "uniform_policy")]
    elif fault == "missing-oci":
        a["lines"] = [r for r in a["lines"] if r["statement"] != "oci"]
    elif fault == "missing-opening":
        a["lines"] = [r for r in a["lines"] if r["kind"] != "opening_equity"]
    elif fault == "duplicate-entity":
        b["legal_entity_id"] = a["legal_entity_id"]
    elif fault == "different-year":
        b["period_start"] = "2025-01-02"
    elif fault == "consolidated":
        a["basis"] = "ifrs10_consolidated"
    elif fault == "currency":
        a["currency"] = "USD"
    elif fault == "partial-membership":
        a["membership_from"] = "2025-02-01"
    elif fault == "missing-counterparty":
        a["lines"][-1]["counterparty_member"] = None
    elif fault == "source-precision":
        a["lines"][0]["amount"] = "1.000000001"
    else:
        data["current"]["basis_of_preparation"] = " " * 15
    with pytest.raises(ValueError):
        result(data)
