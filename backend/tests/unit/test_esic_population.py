"""Fictional member evidence; no legal rate or portal qualification."""

import csv
import io
import uuid
from copy import deepcopy

import pytest
from openpyxl import load_workbook

from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.esic_population import ESICMember
from app.modules.country_workflows.schemas import SourceInput, WorkflowInput
from app.modules.country_workflows.sources import parse_csv
from app.modules.intelligence.exports import render


def population():
    row = {"id": "SYN-1", "registration": "00123456789012345", "period": "2026-06",
           "subject": "0012345678", "member_name": "SYNTHETIC MEMBER ONE", "paid_days": 25,
           "amount": "10000", "currency": "INR", "zero_wage_reason": "", "last_working_day": None,
           "evidence_reference": "SYNTHETIC original payroll", "assessment": "Independently assessed fictional membership and wage evidence"}
    return [row, {**row, "id": "SYN-2", "subject": "0012345679", "member_name": "SYNTHETIC MEMBER TWO",
                  "paid_days": 0, "amount": "0", "zero_wage_reason": "SYN-ASSESSED-LEAVER", "last_working_day": "2026-06-02"}]


def parameters(rows, **changes):
    return SourceInput.model_validate({
        "evidence_version_id": uuid.uuid4(), "table_type": "esic-members", "label": "SYNTHETIC ESIC population",
        "expected_rows": len(rows), "control_totals": {"INR": str(sum(ESICMember.model_validate(row).amount for row in rows))},
        **({"nil_reason": "Independently assessed fictional nil member population"} if not rows else {}),
        "esic_paid_days_control": sum(row["paid_days"] for row in rows),
        "esic_zero_wage_members_control": sum(ESICMember.model_validate(row).amount == 0 for row in rows),
        **changes,
    })


def csv_bytes(rows):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(population()[0]))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode()


def run(payroll=None, reported=None, country="IN", **changes):
    payroll = population() if payroll is None else payroll
    reported = [{**row, "id": "REPORTED-" + row["id"], "evidence_reference": "SYNTHETIC independently reported record"} for row in (payroll if reported is None else reported)]
    sources = {role: parse_csv(csv_bytes(rows), parameters(rows)) for role, rows in (("payroll", payroll), ("reported", reported))}
    data = WorkflowInput.model_validate({"workflow": "india-esic-population", "source_ids": {role: uuid.uuid4() for role in sources},
        "as_of": "2026-06-30", "currency": "INR", "title": "SYNTHETIC ESIC comparison", "rationale": "Independent fictional payroll and reported member populations", **changes})
    return calculate(data, country, sources)


def test_complete_population_retains_zero_wage_member_and_leading_zeros():
    original = population()
    copied = deepcopy(original)
    body = run(original)
    assert original == copied and body["exception_count"] == 0 and not body["blocked"]
    assert body["esic_population_scope"] == {"registration": "00123456789012345", "period": "2026-06"}
    assert body["esic_population_totals"]["payroll"] == {"members": 2, "wages": "10000", "paid_days": 25, "zero_wage_members": 1}
    assert body["rows"][1]["payroll_amount"] == "0" and body["rows"][1]["subject"] == "0012345679"
    assert body["statutory_calculation_qualified"] is False


@pytest.mark.parametrize("field,value,issue", [
    ("paid_days", 24, "PAID_DAY_VARIANCE"), ("member_name", "SYNTHETIC DIFFERENT NAME", "MEMBER_NAME_DIFFERENCE"),
    ("zero_wage_reason", "SYN-DIFFERENT-REASON", "ZERO_WAGE_REASON_DIFFERENCE"),
    ("last_working_day", "2026-06-03", "LAST_WORKING_DAY_DIFFERENCE"),
])
def test_money_tolerance_never_excuses_nonmonetary_difference(field, value, issue):
    reported = population()
    reported[1 if field in {"zero_wage_reason", "last_working_day"} else 0][field] = value
    body = run(reported=reported, tolerance="999999")
    assert body["exception_count"] == 1
    assert issue in next(row["exceptions"] for row in body["rows"] if row["state"] == "EXCEPTIONS")


def test_missing_member_blocks_even_when_wages_equal_and_nil_is_not_missing_scope():
    body = run(reported=population()[:1])
    assert body["blocked"] and body["exception_count"] == 1
    assert body["rows"][1]["exceptions"] == ["MISSING_REPORTED_MEMBER"]
    with pytest.raises(ValueError, match="one explicit ESIC"):
        run(payroll=[], reported=[])


def test_wage_variances_not_netted_across_members_and_source_linkage_preserved():
    p = population()
    p[1].update(amount="4000", paid_days=20, zero_wage_reason="", last_working_day=None)
    reported = deepcopy(p)
    reported[0]["amount"], reported[1]["amount"] = "9000", "5000"
    body = run(p, reported)
    assert body["exception_count"] == 2
    assert [row["wage_difference"] for row in body["rows"]] == ["-1000", "1000"]
    assert body["rows"][0]["payroll_id"] == "SYN-1" and body["rows"][0]["reported_id"] == "REPORTED-SYN-1"


@pytest.mark.parametrize("change,error", [({"currency": "AED"}, "requires INR"), ({"as_of": "2026-06-29"}, "closes after")])
def test_workflow_scope(change, error):
    with pytest.raises(ValueError, match=error):
        run(**change)


def test_wrong_country_duplicate_member_and_mixed_employers_or_months_fail():
    with pytest.raises(ValueError, match="unavailable"):
        run(country="AE")
    for change, error in [({"id": "COPY"}, "Duplicate ESIC"), ({"id": "OTHER", "registration": "99123456789012345"}, "one explicit ESIC"), ({"id": "OTHER", "period": "2026-05"}, "one explicit ESIC")]:
        p = population()
        p.append({**p[0], **change})
        with pytest.raises(ValueError, match=error):
            run(p)


@pytest.mark.parametrize("field,value", [("paid_days", "1.5"), ("paid_days", True), ("paid_days", 31),
    ("period", "0000-01"), ("registration", "123"), ("subject", "123456789"), ("amount", "-1"),
    ("amount", "1.001"), ("last_working_day", "2026-07-01"), ("member_name", " ")])
def test_invalid_member(field, value):
    with pytest.raises(ValueError):
        ESICMember.model_validate({**population()[0], field: value})


def test_explicit_zero_reason_and_independent_source_controls():
    row = population()[1]
    with pytest.raises(ValueError):
        ESICMember.model_validate({**row, "zero_wage_reason": ""})
    for change in ({"esic_paid_days_control": 24}, {"esic_zero_wage_members_control": 0}, {"control_totals": {"INR": "9999"}}):
        with pytest.raises(ValueError, match="control"):
            parse_csv(csv_bytes(population()), parameters(population(), **change))
    with pytest.raises(ValueError, match="independent paid-day"):
        parameters(population(), esic_paid_days_control=None)


def test_xlsx_keeps_member_identity_day_reason_date_and_wage_distinction():
    body = run()
    raw, _ = render({"id": str(uuid.uuid4()), "kind": "country-workflow", "version": 1, "body": body, "dependencies": [], "sha256": "a" * 64, "created_at": "2026-06-30T00:00:00Z"}, "xlsx")
    book = load_workbook(io.BytesIO(raw))
    values = [value for sheet in book for row in sheet.values for value in row]
    assert "0012345679" in values and "SYN-ASSESSED-LEAVER" in values and "2026-06-02" in values


def test_maximum_population_preserves_every_member_and_rejects_control_reuse():
    rows = [{**population()[0], "id": f"SYN-{index}", "subject": f"{index:010d}"} for index in range(5000)]
    body = run(rows)
    assert len(body["rows"]) == 5000 and body["exception_count"] == 0
    assert body["esic_population_totals"]["payroll"]["paid_days"] == 125000
    assert body["rows"][0]["subject"] == "0000000000" and body["rows"][-1]["subject"] == "0000004999"
    with pytest.raises(ValueError, match="apply only"):
        SourceInput.model_validate({"evidence_version_id": uuid.uuid4(), "table_type": "transactions", "label": "SYNTHETIC wrong control", "expected_rows": 1, "esic_paid_days_control": 1})
