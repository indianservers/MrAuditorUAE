import uuid
from datetime import date
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

from app.modules.tax import calculations as c
from app.modules.tax import schemas as s

P = s.RuleParameters()
ID = str(uuid.UUID(int=1))


@pytest.mark.parametrize(
    "income,expected",
    [
        ("-1", "0"),
        ("0", "0"),
        ("374999", "0"),
        ("375000", "0"),
        ("375001", "0.09"),
        ("1000000", "56250"),
    ],
)
def test_standard_bands(income, expected):
    assert c.standard_tax(income, P) == D(expected)


@pytest.mark.parametrize(
    "end,expected",
    [
        (date(2025, 12, 31), date(2026, 9, 30)),
        (date(2025, 6, 30), date(2026, 3, 31)),
        (date(2026, 3, 31), date(2026, 12, 31)),
        (date(2023, 5, 31), date(2024, 2, 29)),
    ],
)
def test_deadlines(end, expected):
    assert c.filing_deadline(end, 9) == expected


def interest_input(**changes):
    return s.Interest.model_validate(
        {
            "profile_id": ID,
            "interest_expense": "20000000",
            "interest_income": "0",
            "depreciation_tax_deductible": "0",
            "taxable_before_gidlr_losses": "30000000",
            "period_months": "12",
            "period_index": 3,
            "statutory_bridge": "Synthetic tax-adjusted bridge, not IFRS EBITDA",
            "loan_and_tp_review": "Synthetic prior general/ALP/specific restriction review",
            **changes,
        }
    )


def test_interest_ebitda_and_threshold():
    result = c.interest(interest_input(), P)
    assert D(result["adjusted_ebitda"]) == 50000000
    assert D(result["limit"]) == 15000000
    assert D(result["current_disallowed"]) == 5000000


def test_interest_small_short_and_capitalised():
    small = c.interest(interest_input(interest_expense="5000000"), P)
    assert D(small["current_disallowed"]) == 0
    short = c.interest(
        interest_input(
            interest_expense="8000000", taxable_before_gidlr_losses="0", period_months="6"
        ),
        P,
    )
    assert D(short["threshold"]) == 6000000 and D(short["current_disallowed"]) == 2000000
    capital = c.interest(
        interest_input(
            interest_expense="8000000",
            capitalised_incurred="9000000",
            capitalised_amortisation="1000000",
            taxable_before_gidlr_losses="0",
        ),
        P,
    )
    assert D(capital["net_interest"]) == 9000000


def test_interest_old_first_and_expiry():
    result = c.interest(
        interest_input(
            interest_expense="19000000",
            taxable_before_gidlr_losses="52000000",
            depreciation_tax_deductible="6000000",
            carryforwards=[
                {
                    "origin_period_index": 2,
                    "balance": "22600000",
                    "origin_source": "Synthetic prior approved ledger",
                }
            ],
        ),
        P,
    )
    assert D(result["limit"]) == 23100000
    assert D(result["carryforward_used"]) == 22600000
    assert D(result["current_deductible"]) == 500000
    expired = c.interest(
        interest_input(
            period_index=12,
            carryforwards=[
                {"origin_period_index": 1, "balance": "10", "origin_source": "Synthetic expired"}
            ],
        ),
        P,
    )
    assert expired["carryforward"][0]["expired"]


def test_interest_excluded_and_invalid():
    result = c.interest(
        interest_input(excluded_taxpayer=True, exclusion_basis="Synthetic bank status evidenced"), P
    )
    assert D(result["current_disallowed"]) == 0
    with pytest.raises(ValueError):
        c.interest(interest_input(excluded_expense="21000000"), P)


def qfzp_input(nonqual="300000", **changes):
    conditions = [
        {
            "requirement": key,
            "assessment": "PASS" if key in c.CORE_QFZP else "NOT_APPLICABLE",
            "rationale": "Synthetic reviewed legal facts",
            "evidence_record_ids": [ID] if key in c.CORE_QFZP else [],
        }
        for key in sorted(c.QFZP_REQUIRED)
    ]
    segment = {
        "source_line_code": "REVENUE",
        "taxable_profit": "0",
        "counterparty": "Synthetic buyer",
        "counterparty_type": "non_free_zone",
        "activity": "Manufacturing, reviewed",
        "jurisdiction": "AE",
        "contract_evidence_id": ID,
        "rationale": "Synthetic contract classification",
    }
    return s.QFZP.model_validate(
        {
            "profile_id": ID,
            "conditions": conditions,
            "segments": [
                {**segment, "reference": "Q", "revenue": "5700000", "classification": "qualifying"},
                {
                    **segment,
                    "reference": "N",
                    "revenue": nonqual,
                    "classification": "nonqualifying",
                },
            ],
            "procedures_applicability_basis": "No distribution activity",
            **changes,
        }
    )


def test_qfzp_de_minimis_and_uncertainty():
    profile = SimpleNamespace(revenue=D("6000000"), free_zone=True)
    passed = c.qfzp(qfzp_input(), profile, P)
    assert passed["assessment"] == "PASS" and D(passed["threshold"]) == 300000
    failed = c.qfzp(qfzp_input("300001"), SimpleNamespace(revenue=D("6000001"), free_zone=True), P)
    assert (
        failed["assessment"] == "FAIL" and failed["disqualification_periods_including_current"] == 5
    )
    data = qfzp_input()
    next(
        x for x in data.conditions if x.requirement == "substance"
    ).assessment = "INSUFFICIENT_DATA"
    assert c.qfzp(data, profile, P)["assessment"] == "INSUFFICIENT_DATA"


def test_qfzp_exclusions_require_legal_category():
    data = qfzp_input()
    data.segments[0].denominator_excluded = True
    with pytest.raises(ValueError):
        c.qfzp(data, SimpleNamespace(revenue=D("6000000"), free_zone=True), P)


def test_sbr_extension_election_and_history():
    profile = SimpleNamespace(
        resident=True,
        tax_start=date(2028, 1, 1),
        tax_end=date(2028, 12, 31),
        revenue=D("3000000"),
        classification="resident_juridical",
        pillar_two_in_scope=False,
    )
    data = s.SBR.model_validate(
        {
            "profile_id": ID,
            "election_made": True,
            "prior_revenues": ["2000000"],
            "prior_periods_complete": True,
            "is_qfzp": False,
            "excluded_multinational": False,
            "artificial_separation": False,
            "aggregation_review": "Synthetic historical/anti-abuse review",
            "election_evidence_id": ID,
        }
    )
    assert not c.small_business(data, profile, P)["eligible_and_elected"]
    amended = s.RuleParameters(sbr_last_period_end=date(2029, 12, 31))
    assert c.small_business(data, profile, amended)["eligible_and_elected"]
    data.prior_revenues = [D("3000001")]
    assert not c.small_business(data, profile, amended)["eligible_and_elected"]


def test_loss_limit_fifo_and_negative_income():
    rows = c.loss_allocation(D("1000000"), D("0.75"), [{"id": ID, "available": "800000"}])
    assert D(rows[0]["used"]) == 750000 and D(rows[0]["closing"]) == 50000
    assert D(c.loss_allocation(-10, D("0.75"), [{"id": ID, "available": "100"}])[0]["used"]) == 0


def test_entertainment_partial_and_provision_not_automatic():
    base = {
        "profile_id": ID,
        "rule_id": ID,
        "account_codes": ["500"],
        "accounting_amount": "100",
        "entertainment_scope": "customers_suppliers_partners",
        "proposed_adjustment": "50",
        "treatment": "partial_deduction",
        "rationale": "Synthetic reviewed category",
        "evidence_record_ids": [ID],
    }
    assert c.adjustment_amount(s.Adjustment(category="entertainment", **base), P) == 50
    assert (
        c.adjustment_amount(
            s.Adjustment(
                category="provision",
                **{**base, "proposed_adjustment": "0", "treatment": "no_adjustment"},
            ),
            P,
        )
        == 0
    )


def test_fta_sampling_bound():
    assert c.sample_size(100) == 50 and c.sample_size(1000) == 91 and c.sample_size(0) == 0
