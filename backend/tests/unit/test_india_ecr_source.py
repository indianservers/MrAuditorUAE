import io
import uuid
from decimal import Decimal

import pytest

from app.modules.audit_execution.evidence import validate_file
from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.native_sources import parse_native
from app.modules.country_workflows.schemas import SourceInput, WorkflowInput

ECR = b"100000000001#~#SYNTHETIC MEMBER ONE#~#20000#~#15000#~#15000#~#15000#~#1800#~#1250#~#550#~#0#~#0\n100000000002#~#SYNTHETIC MEMBER TWO#~#10000#~#10000#~#0#~#10000#~#1200#~#0#~#1200#~#2#~#100\n"


def options(**changes):
    payload = dict(
        evidence_version_id=uuid.uuid4(),
        file_format="india-epfo-ecr",
        table_type="obligations",
        employer_registration="SYNTHETIC-EPFO-001",
        obligation_period="2026-06",
        expected_members=2,
        expected_rows=7,
        control_totals={"INR": "6100"},
        label="SYNTHETIC monthly ECR",
    )
    payload.update(changes)
    return SourceInput(**payload)


def parse(content=ECR, data=None, country="IN"):
    return parse_native(content, data or options(), country, "synthetic-ecr.txt")


def test_monthly_ecr_preserves_wages_components_refund_and_unproven_payment():
    result = parse()
    assert result["row_count"] == 7
    assert sum(Decimal(row["amount"]) for row in result["rows"]) == 6100
    assert all(row["payment_date"] is None and row["due_date"] is None for row in result["rows"])
    assert {row["component"] for row in result["rows"]} == {
        "PF:EMPLOYEE",
        "PF:EPS",
        "PF:EMPLOYER",
        "PF:ADVANCE_REFUND",
    }
    metadata = result["native_metadata"]
    assert metadata["member_count"] == 2
    assert metadata["wage_totals"] == {
        "gross": "30000",
        "epf": "25000",
        "eps": "15000",
        "edli": "25000",
    }
    assert metadata["contribution_totals"] == {
        "employee_pf": "3000",
        "employer_eps": "1250",
        "employer_pf": "1750",
        "advance_refund": "100",
    }
    assert metadata["payment_execution"] == "NOT_EVIDENCED_BY_RETURN_TEXT"
    assert metadata["filing_status"] == "NOT_VERIFIED"
    assert result["statutory_calculation_qualified"] is False
    assert validate_file(io.BytesIO(ECR), "synthetic-ecr.txt") == "text/plain"
    assert validate_file(io.BytesIO(ECR), "synthetic.ecr") == "text/plain"


def test_due_date_is_explicit_and_does_not_create_payment_evidence():
    result = parse(data=options(obligation_due_date="2026-07-15"))
    assert all(
        row["due_date"] == "2026-07-15" and row["payment_date"] is None for row in result["rows"]
    )


def test_return_text_cannot_satisfy_payment_timing_even_when_all_amounts_agree():
    native = parse(data=options(obligation_due_date="2026-07-15"))
    populations = {role: native for role in ("expected", "return", "payment")}
    data = WorkflowInput(
        workflow="statutory-dues",
        source_ids={role: uuid.uuid4() for role in populations},
        as_of="2026-07-31",
        currency="INR",
        title="Synthetic ECR is not payment",
        rationale="Return text cannot establish execution of any bank payment",
    )
    with pytest.raises(ValueError, match="independent expected dues"):
        calculate(data, "IN", populations)


def test_reader_does_not_invent_pension_ceiling_or_derive_contribution_rates():
    content = b"100000000001#~#SYNTHETIC HIGHER PENSION#~#30000#~#30000#~#30000#~#15000#~#3600#~#2500#~#1100#~#0#~#0\n"
    result = parse(
        content, options(expected_members=1, expected_rows=3, control_totals={"INR": "7200"})
    )
    assert result["rows"][0]["eps_wages"] == "30000"
    assert result["native_metadata"]["statutory_rate_validation"] == "NOT_PERFORMED"
    assert result["native_metadata"]["membership_and_exemption_validation"] == "NOT_PERFORMED"


@pytest.mark.parametrize(
    "old,new",
    [
        (b"100000000002", b"100000000001"),
        (b"100000000001", b"000000000000"),
        (b"100000000001", b"10000000001"),
        (b"#~#20000#~#", b"#~#20000.00#~#"),
        (b"#~#20000#~#", b"#~#-20000#~#"),
        (b"#~#20000#~#15000", b"#~#10000#~#15000"),
        (b"#~#15000#~#15000#~#15000", b"#~#15000#~#16000#~#15000"),
        (b"#~#0#~#0\n", b"#~#31#~#0\n"),
        (b"#~#2#~#100", b"#~#2.5#~#100"),
        (b"SYNTHETIC MEMBER ONE", b""),
        (b"SYNTHETIC MEMBER ONE", b"MEMBER\tONE"),
        (b"#~#550#~#0#~#0", b"#~#550#~#0"),
    ],
)
def test_malformed_members_or_layouts_are_rejected(old, new):
    with pytest.raises(ValueError):
        parse(ECR.replace(old, new))


@pytest.mark.parametrize(
    "changes",
    [
        {"expected_members": 1},
        {"expected_rows": 6},
        {"control_totals": {"INR": "6000"}},
        {"obligation_period": None},
        {"employer_registration": None},
        {"expected_members": None},
        {"employer_registration": "wrong registration"},
    ],
)
def test_explicit_context_and_independent_controls_required(changes):
    with pytest.raises(ValueError):
        parse(data=options(**changes))


def test_country_boundary_and_utf8_text_safety():
    with pytest.raises(ValueError, match="country"):
        parse(country="AE")
    with pytest.raises(ValueError, match="UTF-8"):
        parse(ECR.replace(b"MEMBER ONE", b"\xff"))
    with pytest.raises(ValueError):
        validate_file(io.BytesIO(b"\xff"), "bad.txt")
    with pytest.raises(ValueError):
        validate_file(io.BytesIO(b"x\x01"), "bad.txt")


def test_zero_wages_and_full_non_contributory_month_are_not_a_nil_source():
    content = b"100000000001#~#SYNTHETIC MEMBER#~#0#~#0#~#0#~#0#~#0#~#0#~#0#~#29#~#0\n"
    result = parse(
        content,
        options(
            obligation_period="2024-02",
            expected_members=1,
            expected_rows=3,
            control_totals={"INR": "0"},
        ),
    )
    assert result["row_count"] == 3 and result["nil_reason"] is None
    with pytest.raises(ValueError, match="calendar days"):
        parse(
            content,
            options(
                obligation_period="2025-02",
                expected_members=1,
                expected_rows=3,
                control_totals={"INR": "0"},
            ),
        )
