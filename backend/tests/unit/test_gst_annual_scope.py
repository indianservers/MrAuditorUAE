from calendar import monthrange
from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.modules.country_workflows.gst_annual_scope import AnnualGSTScope, saved_current
from app.modules.country_workflows.review import approval_error
from tests.unit.test_turnover_bridge import compare, populations


def scope(**changes):
    return dict(
        pan="ABCDE1234F",
        financial_year_start="2025-04-01",
        financial_year_end="2026-03-31",
        rule_review_date="2026-10-30",
        taxpayer_type="regular",
        aggregate_turnover="20000000",
        other_pan_turnover="0",
        pan_population_complete=True,
        assessment="SYNTHETIC independently assessed all-PAN turnover and legal status",
        **changes,
    )


def annual_rows(amount="20000000", registrations=1):
    rows = populations("IN")
    for role, population in rows.items():
        population[0].update(period_start="2025-04-01", period_end="2026-03-31")
        if role != "scope":
            population[0]["amount"] = amount if role in {"books", "return"} else "0"
        if role == "adjustments":
            population[0]["reason"] = "assessed-nil"
        if registrations == 2:
            population.append(
                dict(population[0], id="second-" + role, registration="27ABCDE1234F1Z5")
            )
    return rows


def monthly_and_quarterly_rows():
    """Two independently assessed registrations with different filing partitions."""
    originals = annual_rows()
    rows = {role: [] for role in originals}
    months = [(2025, month) for month in range(4, 13)] + [(2026, month) for month in range(1, 4)]
    monthly = [
        (f"{year}-{month:02}-01", f"{year}-{month:02}-{monthrange(year, month)[1]}")
        for year, month in months
    ]
    quarterly = [
        ("2025-04-01", "2025-06-30"),
        ("2025-07-01", "2025-09-30"),
        ("2025-10-01", "2025-12-31"),
        ("2026-01-01", "2026-03-31"),
    ]
    for registration, partitions, amount in [
        ("29ABCDE1234F1Z5", monthly, "2000000"),
        ("27ABCDE1234F1Z5", quarterly, "7000000"),
    ]:
        for start, end in partitions:
            for role in originals:
                row = dict(
                    originals[role][0],
                    id=f"{role}-{registration[:2]}-{start}",
                    registration=registration,
                    period_start=start,
                    period_end=end,
                )
                if role != "scope":
                    row.update(
                        reference=f"{role}-{start}", amount="0" if role == "adjustments" else amount
                    )
                rows[role].append(row)
    return rows


def partitioned_scope():
    facts = scope()
    facts["aggregate_turnover"] = "52000000"
    return facts


def test_monthly_and_quarterly_gstins_cover_one_pan_year_without_double_counting():
    result = compare(monthly_and_quarterly_rows(), "IN", gst_annual_scope=partitioned_scope())
    assessment = result["annual_gst_assessment"]
    assert len(result["rows"]) == 16 and all(row["state"] == "MATCHED" for row in result["rows"])
    assert assessment["registration_turnover"] == "52000000" and assessment["pending_reasons"] == []
    assert assessment["gstr9c"] == "CANDIDATE_REQUIRED_SELF_CERTIFIED" and not result["blocked"]


def test_missing_interior_month_is_pending_even_when_every_supplied_amount_and_pan_control_agree():
    rows = monthly_and_quarterly_rows()
    for role in rows:
        rows[role] = [
            row
            for row in rows[role]
            if not (row["registration"].startswith("29") and row["period_start"] == "2025-06-01")
        ]
    facts = partitioned_scope()
    facts["aggregate_turnover"] = "50000000"
    result = compare(rows, "IN", gst_annual_scope=facts)
    assert all(row["state"] == "MATCHED" for row in result["rows"])
    assert result["annual_gst_assessment"]["pending_reasons"] == [
        "REGISTRATION_YEAR_COVERAGE_INCOMPLETE"
    ]
    assert result["blocked"] and result["annual_gst_assessment"]["gstr9c"] == "PENDING_REVIEW"


def test_equal_opposite_partition_differences_cannot_clear_annual_scope_with_tolerance():
    rows = monthly_and_quarterly_rows()
    rows["return"][0]["amount"] = "2000001"
    rows["return"][-1]["amount"] = "6999999"
    result = compare(rows, "IN", gst_annual_scope=partitioned_scope(), tolerance="2")
    assert all(row["state"] == "MATCHED" for row in result["rows"])
    assert result["annual_gst_assessment"]["registration_turnover"] == "52000000"
    assert result["annual_gst_assessment"]["pending_reasons"] == ["UNRESOLVED_TURNOVER_BRIDGE"]
    assert result["blocked"] and approval_error(result)


def test_annual_partition_cannot_duplicate_monthly_coverage_in_the_same_registration():
    rows = monthly_and_quarterly_rows()
    rows["scope"].append(
        dict(rows["scope"][0], id="duplicate-annual-scope", period_end="2026-03-31")
    )
    with pytest.raises(ValueError, match="Overlapping expected registration periods"):
        compare(rows, "IN", gst_annual_scope=partitioned_scope())


def run(amount="20000000", **changes):
    facts = scope()
    facts.update(aggregate_turnover=amount, **changes)
    return compare(annual_rows(amount), "IN", gst_annual_scope=facts)


@pytest.mark.parametrize(
    "amount,annual,reconciliation",
    [
        ("0", "CANDIDATE_EXEMPT_UP_TO_2_CRORE", "CANDIDATE_THRESHOLD_NOT_EXCEEDED"),
        ("20000000", "CANDIDATE_EXEMPT_UP_TO_2_CRORE", "CANDIDATE_THRESHOLD_NOT_EXCEEDED"),
        ("20000000.00000001", "CANDIDATE_REQUIRED", "CANDIDATE_THRESHOLD_NOT_EXCEEDED"),
        ("50000000", "CANDIDATE_REQUIRED", "CANDIDATE_THRESHOLD_NOT_EXCEEDED"),
        ("50000000.00000001", "CANDIDATE_REQUIRED", "CANDIDATE_REQUIRED_SELF_CERTIFIED"),
    ],
)
def test_exact_thresholds_preserve_candidates_without_filing_or_professional_qualification(
    amount, annual, reconciliation
):
    result = run(amount)
    assessment = result["annual_gst_assessment"]
    assert assessment["gstr9"] == annual and assessment["gstr9c"] == reconciliation
    assert (
        not assessment["statutory_qualification"]
        and assessment["filing_status"] == "NOT_ESTABLISHED"
    )
    assert not result["blocked"] and approval_error(result) is None and saved_current(result)


def test_multiple_gstins_and_explicit_other_pan_turnover_are_not_single_registration_thresholds():
    facts = scope()
    facts.update(aggregate_turnover="50000001", other_pan_turnover="10000001")
    result = compare(annual_rows(registrations=2), "IN", gst_annual_scope=facts)
    assert result["annual_gst_assessment"]["registration_turnover"] == "40000000"
    assert result["annual_gst_assessment"]["gstr9c"] == "CANDIDATE_REQUIRED_SELF_CERTIFIED"


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"aggregate_turnover": None}, "PAN_TURNOVER_CONTROL_MISSING"),
        ({"other_pan_turnover": None}, "PAN_TURNOVER_CONTROL_MISSING"),
        ({"other_pan_turnover": "1"}, "PAN_TURNOVER_CONTROL_VARIANCE"),
        ({"pan_population_complete": False}, "PAN_POPULATION_NOT_ASSESSED_COMPLETE"),
        ({"taxpayer_type": "unknown"}, "TAXPAYER_STATUS_REQUIRES_SEPARATE_REVIEW"),
        ({"taxpayer_type": "mixed"}, "TAXPAYER_STATUS_REQUIRES_SEPARATE_REVIEW"),
        ({"taxpayer_type": "composition"}, "TAXPAYER_STATUS_REQUIRES_SEPARATE_REVIEW"),
        ({"rule_review_date": "2025-09-16"}, "OUTSIDE_ASSESSED_RULE_REVIEW_WINDOW"),
        ({"rule_review_date": "2026-10-31"}, "OUTSIDE_ASSESSED_RULE_REVIEW_WINDOW"),
    ],
)
def test_missing_or_unresolved_facts_block_without_zero_or_exemption(changes, reason):
    facts = scope()
    facts.update(changes)
    result = compare(annual_rows(), "IN", gst_annual_scope=facts)
    assert reason in result["annual_gst_assessment"]["pending_reasons"]
    assert result["annual_gst_assessment"]["gstr9"] == "PENDING_REVIEW" and result["blocked"]
    assert approval_error(result)


@pytest.mark.parametrize(
    "kind",
    [
        "isd",
        "section-51",
        "section-52",
        "casual",
        "non-resident",
        "government-local-authority-audited",
    ],
)
def test_explicit_assessed_excluded_status_is_not_a_zero_turnover_decision(kind):
    assert (
        run("60000000", taxpayer_type=kind)["annual_gst_assessment"]["gstr9"]
        == "CANDIDATE_SECTION_44_EXCLUSION"
    )


def test_partial_year_and_unexplained_variance_remain_pending_even_with_huge_tolerance():
    rows = annual_rows()
    for population in rows.values():
        population[0]["period_start"] = "2025-05-01"
    result = compare(rows, "IN", gst_annual_scope=scope())
    assert (
        "REGISTRATION_YEAR_COVERAGE_INCOMPLETE"
        in result["annual_gst_assessment"]["pending_reasons"]
    )
    rows = annual_rows()
    rows["return"][0]["amount"] = "19999999"
    result = compare(rows, "IN", gst_annual_scope=scope(), tolerance="100")
    assert "UNRESOLVED_TURNOVER_BRIDGE" in result["annual_gst_assessment"]["pending_reasons"]


def test_country_pan_and_year_boundaries_and_saved_contract():
    with pytest.raises(ValueError, match="only for India"):
        compare(populations("AE"), "AE", gst_annual_scope=scope())
    facts = scope()
    facts["pan"] = "ZZZZZ1234F"
    with pytest.raises(ValueError, match="declared PAN"):
        compare(annual_rows(), "IN", gst_annual_scope=facts)
    facts = scope()
    facts["financial_year_end"] = "2026-03-30"
    with pytest.raises(ValidationError, match="April-March"):
        AnnualGSTScope(**facts)
    result = run()
    original = deepcopy(result)
    result["annual_gst_assessment"].pop("contract")
    assert not saved_current(result) and "Regenerate annual GST" in approval_error(result)
    assert original["annual_gst_assessment"]["contract"]
    assert saved_current(compare(country="IN"))


@pytest.mark.parametrize("year,pending", [(2023, True), (2024, False), (2026, True)])
def test_rule_years_do_not_extend_automatically(year, pending):
    facts = scope()
    facts.update(financial_year_start=f"{year}-04-01", financial_year_end=f"{year + 1}-03-31")
    rows = annual_rows()
    for population in rows.values():
        for row in population:
            row.update(period_start=f"{year}-04-01", period_end=f"{year + 1}-03-31")
    if year == 2026:
        # The financial year is deliberately still open; test the assessor directly.
        from datetime import date

        from app.modules.country_workflows.gst_annual_scope import assess

        comparison = {
            "rows": [
                {
                    "registration": "29ABCDE1234F1Z5",
                    "period_start": "2026-04-01",
                    "period_end": "2027-03-31",
                    "expected_return_turnover": "20000000",
                    "difference": "0",
                    "state": "MATCHED",
                }
            ]
        }
        assessment = assess(AnnualGSTScope(**facts), comparison, "IN", date(2026, 10, 30))
        assert "FINANCIAL_YEAR_NOT_CLOSED" in assessment["pending_reasons"]
    else:
        assessment = compare(rows, "IN", gst_annual_scope=facts)["annual_gst_assessment"]
    assert (assessment["gstr9"] == "PENDING_REVIEW") == pending
