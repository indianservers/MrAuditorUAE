from copy import deepcopy
from decimal import getcontext, localcontext

import pytest
from pydantic import ValidationError

from app.modules.audit_execution.schemas import Finding
from app.modules.regulatory.exposure_rollup import ExposureRollupInput, summarize


def finding(identifier="f", amount="100", currency="AED", status="ACCEPTED_UNRESOLVED", **changes):
    return {
        "id": identifier,
        "reference": identifier,
        "status": status,
        "body": {"financial_impact": amount, "financial_impact_currency": currency, **changes},
    }


def paper(identifier, *sources):
    return {
        "id": identifier,
        "body": {"sources": [{"kind": "record", "id": source} for source in sources]},
    }


def test_exact_identity_deduplicates_across_papers_without_netting_or_fx():
    papers = [paper("gst", "f"), paper("tax-audit", "f", "n", "inr")]
    findings = {"f": finding(), "n": finding("n", "-20"), "inr": finding("inr", "50", "INR")}
    source = deepcopy((papers, findings))
    result = summarize(papers, findings)
    assert result["unique_findings"] == 3 and result["workpaper_reference_count"] == 4
    assert result["duplicate_references_eliminated"] == 1
    assert result["totals_by_currency"] == {
        "AED": {"positive_impact": "100", "negative_impact": "-20", "finding_count": 2},
        "INR": {"positive_impact": "50", "negative_impact": "0", "finding_count": 1},
    }
    assert result["rows"][0]["workpaper_ids"] == ["gst", "tax-audit"]
    assert not result["blocked"] and source == (papers, findings)


@pytest.mark.parametrize(
    "amount,currency,status,code",
    [
        (None, "AED", "CLOSED", "IMPACT_UNQUANTIFIED"),
        ("0", None, "CLOSED", "IMPACT_CURRENCY_UNASSESSED"),
        ("0", "AED", "OPEN", "FINDING_REVIEW_REQUIRED"),
    ],
)
def test_unknown_or_unreviewed_does_not_become_zero(amount, currency, status, code):
    result = summarize(
        [paper("p", "f")], {"f": finding(amount=amount, currency=currency, status=status)}
    )
    assert result["blocked"] and not result["totals_by_currency"]
    assert code in result["rows"][0]["issues"]


def test_distinct_findings_with_equal_amounts_are_not_fuzzy_duplicates():
    result = summarize([paper("p", "f", "g")], {"f": finding(), "g": finding("g")})
    assert result["unique_findings"] == 2 and result["duplicate_references_eliminated"] == 0
    assert result["totals_by_currency"]["AED"]["positive_impact"] == "200"


def test_zero_and_declared_correction_preserve_gross_source_amounts():
    result = summarize(
        [paper("p", "f", "z")],
        {"f": finding(correction_status="corrected"), "z": finding("z", "0")},
    )
    assert result["totals_by_currency"]["AED"]["positive_impact"] == "100"
    assert result["totals_by_currency"]["AED"]["finding_count"] == 2
    assert result["rows"][0]["correction_status"] == "corrected"


def test_unlinked_paper_blocks_scope_completion():
    result = summarize([paper("empty"), paper("other", "f")], {"f": finding()})
    assert (
        result["blocked"]
        and {"source_id": "empty", "code": "NO_LINKED_AUDIT_FINDING"} in result["issues"]
    )


def test_local_decimal_arithmetic_retains_precision_and_callers_context():
    with localcontext() as arithmetic:
        arithmetic.prec = 5
        before = dict(arithmetic.flags)
        result = summarize(
            [paper("p", "f", "g")],
            {"f": finding(amount="99999999999999999999.99999999"), "g": finding("g", "0.00000001")},
        )
        assert (
            result["totals_by_currency"]["AED"]["positive_impact"]
            == "100000000000000000000.00000000"
        )
        assert (
            getcontext() is arithmetic and arithmetic.prec == 5 and dict(arithmetic.flags) == before
        )


@pytest.mark.parametrize("currency", ["ZZZ", "aed", ""])
def test_invalid_impact_currency_is_not_accepted(currency):
    with pytest.raises(ValidationError):
        Finding(
            finding_type="compliance",
            severity="medium",
            financial_impact="1",
            financial_impact_currency=currency,
        )


def test_duplicate_source_papers_are_rejected():
    u = "00000000-0000-4000-8000-000000000001"
    with pytest.raises(ValidationError):
        ExposureRollupInput(
            workpaper_ids=[u, u], title="Synthetic", rationale="Synthetic explicit population"
        )


def test_analytics_finding_links_are_explicitly_unresolved_even_alongside_a_reviewed_finding():
    source = paper("p", "f")
    source["body"]["sources"].append({"kind": "finding", "id": "analytics-finding"})
    result = summarize([source], {"f": finding()})
    assert result["blocked"] and any(
        issue["code"] == "ANALYTICS_FINDING_REQUIRES_AUDIT_FINDING_ASSESSMENT"
        for issue in result["issues"]
    )
    assert result["totals_by_currency"]["AED"]["positive_impact"] == "100"


@pytest.mark.parametrize(
    "amount,currency,unknown_field",
    [("10", None, "unassessed_currency_ids"), (None, "AED", "unquantified_ids")],
)
def test_completion_register_does_not_report_unassessed_values_as_zero(
    amount, currency, unknown_field
):
    from types import SimpleNamespace

    from app.modules.audit_execution.impact_register import misstatement_register

    row = SimpleNamespace(
        id="f",
        kind="findings",
        body={
            "finding_type": "misstatement",
            "financial_impact": amount,
            "financial_impact_currency": currency,
        },
    )
    result = misstatement_register([row])
    assert result["corrected_gross"] is None and result["uncorrected_gross"] is None
    assert result[unknown_field] == ["f"]


def test_completion_register_never_combines_currencies_or_offsets_gross_impacts():
    from types import SimpleNamespace

    from app.modules.audit_execution.impact_register import misstatement_register

    rows = [
        SimpleNamespace(
            id="a",
            kind="findings",
            body={
                "finding_type": "misstatement",
                "financial_impact": "-20",
                "financial_impact_currency": "AED",
                "correction_status": "corrected",
            },
        ),
        SimpleNamespace(
            id="u",
            kind="findings",
            body={
                "finding_type": "misstatement",
                "financial_impact": "10",
                "financial_impact_currency": "USD",
            },
        ),
    ]
    result = misstatement_register(rows)
    assert result["corrected_gross"] is None and result["summary_currency"] is None
    assert result["totals_by_currency"] == {
        "AED": {"corrected_gross": "20", "uncorrected_gross": "0"},
        "USD": {"corrected_gross": "0", "uncorrected_gross": "10"},
    }
    one = misstatement_register(rows[:1])
    assert one["summary_currency"] == "AED" and one["corrected_gross"] == "20"
    assert misstatement_register([])["corrected_gross"] == "0"
