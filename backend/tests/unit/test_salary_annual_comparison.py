"""All-quarter employee comparisons use current-employer tax, not annual mixed credits."""

from copy import deepcopy
from uuid import uuid4

import pytest

from app.modules.country_workflows.salary_annual_comparison import (
    SalaryAnnualComparisonInput,
    compare,
)


def sample():
    ids = {q: uuid4() for q in ("Q1", "Q2", "Q3", "Q4")}
    data = {
        "label": "SYNTHETIC independently mapped four-quarter salary",
        "quarter_source_ids": ids,
        "crosswalk_document_version_id": uuid4(),
        "crosswalk_sha256": "a" * 64,
        "assessment": "SYNTHETIC full four-quarter and annual SD population, not client qualification",
        "employees": [
            {
                "annual_key": "SD/1/1",
                "parties": [{"quarter": q, "party_key": "1/1/1"} for q in ids],
                "identity_status": "assessed_same_employee",
                "assessment": "SYNTHETIC independently retained same-employee evidence across four quarters",
            }
        ],
    }
    sources = {
        q: {
            "native_format": "india-24q-regular-q4-v7.5"
            if q == "Q4"
            else "india-24q-regular-q1q3-v6.3",
            "table_type": "withholding-records",
            "allowed_source_roles": ["reported"],
            "native_metadata": {
                "form": "24Q",
                "quarter": q,
                "financial_year": "202425",
                "tan": "MUMN77777A",
                "controls": {"record_status": "current"},
                "party_count": 1,
                "party_links": [
                    {
                        "party_key": "1/1/1",
                        "pan": "AAAPA1234A",
                        "total_tax": "100.00",
                        "native_section_code": "92B",
                        "source_line": 4,
                    }
                ],
            },
        }
        for q in ids
    }
    fields = [""] * 88
    fields[28] = "999.00"  # Includes other credits; never the comparison target.
    fields[35] = "400.00"
    sources["Q4"]["native_metadata"]["salary_annual"] = {
        "contract": "historical-salary-annual-observations/1",
        "records": [
            {
                "record_type": "SD",
                "batch": 1,
                "record_number": 1,
                "source_line": 5,
                "pan": "AAAPA1234A",
                "fields": fields,
            }
        ],
    }
    return data, sources


def run(data, sources):
    return compare(SalaryAnnualComparisonInput.model_validate(data), sources)


def test_complete_four_quarters_match_field36_and_retain_every_original_party():
    data, sources = sample()
    result = run(data, sources)
    assert result["rows"][0]["annual_current_employer_tax"] == "400.00"
    assert result["rows"][0]["quarterly_tax"] == "400.00"
    assert result["rows"][0]["comparison_state"] == "AGREES"
    assert len(result["salary_quarterly_links"]) == 4
    assert result["exception_count"] == 0 and result["comparison_complete"]
    assert not result["statutory_calculation_qualified"]


def test_difference_is_preserved_and_is_not_a_recomputed_tax_liability():
    data, sources = sample()
    sources["Q4"]["native_metadata"]["salary_annual"]["records"][0]["fields"][35] = "399.99"
    row = run(data, sources)["rows"][0]
    assert row["difference"] == "-0.01" and row["comparison_state"] == "DIFFERENCE"
    assert row["state"] == "EXCEPTION"


def test_absent_declared_quarter_is_not_implicitly_zero():
    data, sources = sample()
    del sources["Q1"]
    with pytest.raises(ValueError, match="Every declared"):
        run(data, sources)


def test_unassigned_parties_require_documented_exception_disposition_before_approval():
    from app.modules.country_workflows.review import approval_error

    data, sources = sample()
    data["employees"][0]["parties"] = data["employees"][0]["parties"][1:]
    result = run(data, sources)
    result["salary_crosswalk_document_binding"] = "RETAINED_DOCUMENT_BYTES_VERIFIED"
    assert result["rows"][-1]["state"] == "EXCEPTION"
    assert "disposition" in approval_error(result)


@pytest.mark.parametrize("pan", ["PANNOTAVBL", "PANAPPLIED", "PANINVALID", "AAAPA1234A"])
def test_unresolved_employee_identity_never_becomes_agreement_from_equal_amounts_or_names(pan):
    data, sources = sample()
    data["employees"][0]["identity_status"] = "unresolved"
    sources["Q1"]["native_metadata"]["party_links"][0]["pan"] = pan
    result = run(data, sources)
    assert result["rows"][0]["comparison_state"] == "IDENTITY_UNRESOLVED"
    assert not result["comparison_complete"]


def test_assessed_nil_quarter_is_explicit_zero_and_does_not_establish_filing():
    data, sources = sample()
    data["quarter_source_ids"]["Q1"] = None
    data["nil_quarter_assessments"] = {
        "Q1": "SYNTHETIC independently assessed nil employer salary party population"
    }
    data["employees"][0]["parties"] = data["employees"][0]["parties"][1:]
    del sources["Q1"]
    row = run(data, sources)["rows"][0]
    assert row["q1_tax"] == "0" and row["difference"] == "100.00"


def test_unassigned_parties_stay_visible_including_specified_seniors():
    data, sources = sample()
    data["employees"][0]["parties"] = data["employees"][0]["parties"][1:]
    sources["Q1"]["native_metadata"]["party_links"][0]["native_section_code"] = "94P"
    result = run(data, sources)
    assert result["unassigned_quarterly_parties"][0]["native_section_code"] == "94P"
    assert result["exception_count"] == 2 and not result["comparison_complete"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("financial_year", "202324"),
        ("tan", "MUMN77778A"),
        ("quarter", "Q2"),
        ("form", "26Q"),
        ("party_count", 2),
    ],
)
def test_quarter_identity_and_population_cannot_drift(field, value):
    data, sources = sample()
    sources["Q1"]["native_metadata"][field] = value
    with pytest.raises(ValueError):
        run(data, sources)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-quarter",
        "missing-nil-assessment",
        "duplicate-source",
        "duplicate-annual",
        "duplicate-party",
        "empty-assessment",
        "nil-q4",
    ],
)
def test_complete_input_prevents_missing_or_duplicated_populations(mutation):
    data, _ = sample()
    if mutation == "missing-quarter":
        del data["quarter_source_ids"]["Q1"]
    elif mutation == "missing-nil-assessment":
        data["quarter_source_ids"]["Q1"] = None
    elif mutation == "duplicate-source":
        data["quarter_source_ids"]["Q1"] = data["quarter_source_ids"]["Q2"]
    elif mutation == "duplicate-annual":
        data["employees"].append(deepcopy(data["employees"][0]))
    elif mutation == "duplicate-party":
        data["employees"][0]["parties"].append(deepcopy(data["employees"][0]["parties"][0]))
    elif mutation == "nil-q4":
        data["quarter_source_ids"]["Q4"] = None
    else:
        data["employees"][0]["assessment"] = " " * 20
    with pytest.raises(ValueError):
        SalaryAnnualComparisonInput.model_validate(data)


@pytest.mark.parametrize(
    "mutation",
    [
        "old-year",
        "wrong-profile",
        "superseded",
        "missing-annual",
        "missing-field36",
        "unmapped-annual",
        "unknown-party",
        "different-pan",
        "senior-to-salary",
        "duplicate-native-party",
    ],
)
def test_incompatible_or_incomplete_original_context_is_rejected(mutation):
    data, sources = sample()
    m = sources["Q1"]["native_metadata"]
    annual = sources["Q4"]["native_metadata"]["salary_annual"]
    if mutation == "old-year":
        sources["Q4"]["native_metadata"]["financial_year"] = "201213"
    elif mutation == "wrong-profile":
        sources["Q1"]["native_format"] = "canonical-csv"
    elif mutation == "superseded":
        m["controls"]["record_status"] = "superseded"
    elif mutation == "missing-annual":
        del sources["Q4"]["native_metadata"]["salary_annual"]
    elif mutation == "missing-field36":
        annual["records"][0]["fields"][35] = ""
    elif mutation == "unmapped-annual":
        data["employees"][0]["annual_key"] = "SD/1/2"
    elif mutation == "unknown-party":
        data["employees"][0]["parties"][0]["party_key"] = "1/1/2"
    elif mutation == "different-pan":
        m["party_links"][0]["pan"] = "BBBPA1234B"
    elif mutation == "senior-to-salary":
        m["party_links"][0]["native_section_code"] = "94P"
    else:
        m["party_links"].append(deepcopy(m["party_links"][0]))
        m["party_count"] = 2
    with pytest.raises(ValueError):
        run(data, sources)
