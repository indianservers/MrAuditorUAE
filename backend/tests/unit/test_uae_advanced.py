import uuid
from copy import deepcopy
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.modules.audit_execution.schemas import WorkingPaper
from app.modules.jurisdictions.ae.advanced import Schedule, calculate
from app.modules.jurisdictions.ae.advanced_specs import spec

SOURCE = str(uuid.UUID(int=1))


def fixture(i):
    row = {"reference": f"SYN-{i}", "evidence_id": SOURCE}
    for f in spec(i)["fields"]:
        row[f["name"]] = {
            "n": "1",
            "d": "1",
            "b": True,
            "x": "2026-01-01",
            "y": None,
            "t": "SYNTHETIC",
        }[f["type"]]
    if i == 56:
        row.update(transaction_date="2026-02-01", member_from="2026-01-01", member_to="2026-12-31")
    if i == 64:
        row.update(
            foreign_tax="100",
            foreign_currency="USD",
            fx_rate="3.67",
            domestic_attributable_tax="300",
            previously_credited="20",
        )
    if i == 72:
        row.update(
            carrying="1200",
            tax_base="1000",
            enacted_rate="0.09",
            recognition_fraction="1",
            current_tax="90",
            recorded_tax_expense="108",
            opening_deferred="0",
            accounting_profit="1000",
        )
    if i == 75:
        row.update(
            principal="10000", annual_rate="0.05", days="90", day_basis="360", recorded_charge="125"
        )
    if i == 81:
        row.update(event_date="2026-02-01", year_end="2025-12-31", review_date="2026-03-01")
    if i == 83:
        row.update(
            receipt_date="2025-12-31",
            year_end="2025-12-31",
            payment_date="2026-01-02",
            payment="100",
            recorded_accrual="40",
        )
    if i == 88:
        row.update(
            cash_flow="100",
            sensitivity_shift="0.01",
            growth="0",
            discount_rate="0.1",
            terminal_growth="0",
            periods="1",
            recorded_value="1000",
        )
    if i == 91:
        row.update(
            ordered_qty="10",
            order_currency="AED",
            received_qty="8",
            returned_qty="1",
            invoiced_qty="8",
            unit_price="10",
            invoice_net="80",
            fx_rate="1",
            tolerance="0.01",
        )
    return dict(
        use_case_id=i,
        period_start="2026-01-01",
        period_end="2026-12-31",
        currency="AED",
        policy=dict(
            source_id=SOURCE,
            source_locator="SYNTHETIC policy section 1",
            version="SYN1",
            kind="legislation" if i <= 72 or i == 80 else "accounting_requirement",
            effective_from="2026-01-01",
            effective_to="2026-12-31",
            adoption_assessment="SYNTHETIC independently reviewed assumptions, no legal conclusion",
        ),
        assumptions=["SYNTHETIC reviewed inputs"],
        rows=[row],
    )


@pytest.mark.parametrize("i", range(51, 101))
def test_every_distinct_case_has_closed_validated_reproducible_evidenced_output(i):
    data = fixture(i)
    result = calculate(Schedule.model_validate(data))
    assert result == calculate(Schedule.model_validate(deepcopy(data)))
    assert result["use_case_id"] == i and result["rows"][0]["evidence_id"] == SOURCE
    assert result["professional_conclusion"] is None
    assert result["publication"] == "NOT_POSTED_NOT_SENT_NOT_SUBMITTED"
    assert result["review_status"] == "UNREVIEWED"
    data["rows"][0]["send"] = True
    with pytest.raises(ValidationError):
        Schedule.model_validate(data)


@pytest.mark.parametrize(
    "i,key,expected",
    [
        (52, "recoverable", "2"),
        (59, "expected_net_settlement", "2"),
        (62, "expected_net_settlement", "-3"),
        (64, "remaining_candidate_credit", "280"),
        (65, "reviewed_tax_base", "2"),
        (66, "expected_closing", "1"),
        (72, "expected_tax_expense", "108"),
        (74, "expected_royalty", "1"),
        (75, "expected_charge", "125"),
        (76, "unposted_true_up", "0"),
        (78, "adjusted_profit", "0"),
        (80, "expected_closing", "2"),
        (83, "potential_unrecorded_liability", "60"),
        (84, "reviewed_expected_value", "1"),
        (86, "provisional_goodwill", "3"),
        (87, "book_value_equity_bridge", "0"),
        (88, "reviewed_model_value", "1000"),
        (90, "restated_opening", "2"),
        (91, "expected_invoice_net", "80"),
        (92, "unposted_adjustment", "0"),
        (93, "expected_balance", "2"),
        (94, "unrestricted_cash", "0"),
        (95, "refund_and_dispute_total", "3"),
        (97, "reported_integrity_issues", "5"),
        (99, "unresolved_reporting_issues", "4"),
        (100, "completion_blockers", "4"),
    ],
)
def test_independently_calculated_schedule_values(i, key, expected):
    got = calculate(Schedule.model_validate(fixture(i)))["rows"][0]["calculations"][key]
    assert abs(got - Decimal(expected)) < Decimal("0.00000001")


def test_risks_and_cutoffs_have_actual_specific_exceptions():
    expected = {
        51: "recharge_review",
        56: "intragroup_tax_review",
        69: "partner_allocation_difference",
        73: "duplication",
        77: "potentially_omitted_related_transaction",
        82: "response_not_authenticated",
        85: "covenant_breach_for_classification_review",
        91: "quantity_exception",
        96: "supplier_payment_conflict",
        98: "potential_independence_conflict",
    }
    for i, code in expected.items():
        data = fixture(i)
        r = data["rows"][0]
        if i == 51:
            r["agent"] = False
        if i == 69:
            r["allocation_total"] = "0.5"
        if i == 77:
            r["declared"] = False
        if i == 82:
            r["response_authenticated"] = False
        if i == 85:
            r["contractual_limit"] = "0.5"
        assert code in calculate(Schedule.model_validate(data))["rows"][0]["exceptions"]


def test_duplicates_nonfinite_missing_boolean_and_expired_rules_fail_closed():
    for mutate in [
        lambda d: d["rows"].append(deepcopy(d["rows"][0])),
        lambda d: d["rows"][0].update(direct_recoverable="NaN"),
        lambda d: d["policy"].update(effective_to="2026-06-30"),
        lambda d: d.update(currency="XYZ"),
    ]:
        data = fixture(52)
        mutate(data)
        with pytest.raises(ValidationError):
            Schedule.model_validate(data)
    data = fixture(51)
    data["rows"][0]["agent"] = "true"
    with pytest.raises(ValidationError):
        Schedule.model_validate(data)


def test_structured_paper_requires_all_sources_and_inherits_access():
    body = dict(
        folder="SYN",
        sections=[dict(heading="Input", text="SYN")],
        conclusion="Unreviewed",
        advanced_input=fixture(52),
    )
    with pytest.raises(ValidationError):
        WorkingPaper.model_validate(body)
    body["sources"] = [dict(kind="record", id=SOURCE)]
    assert WorkingPaper.model_validate(body).inherit_source_permissions
