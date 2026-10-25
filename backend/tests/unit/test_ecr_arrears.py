"""Fictional eight-field arrears; employer EPF and pension must retain their positions."""

import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.modules.country_workflows.native_sources import parse_native
from app.modules.country_workflows.schemas import SourceInput
from tests.unit.test_india_ecr_source import ECR as MONTHLY

ARREARS = b"100000000001#~#SYNTHETIC ARREAR ONE#~#1000#~#1000#~#1000#~#120#~#37#~#83\n100000000002#~#SYNTHETIC ARREAR TWO#~#500#~#0#~#500#~#60#~#60#~#0\n"
CONTEXT = b"SYNTHETIC ONLY: establishment SYNTHETIC-EPFO-001; all listed members attributed to wage month 2026-06; salary arrear disbursement 2026-07-10. No filing or bank payment confirmation."


def options(**changes):
    return SourceInput.model_validate(
        {
            "evidence_version_id": uuid.uuid4(),
            "file_format": "india-epfo-arrear-ecr-v2",
            "table_type": "obligations",
            "employer_registration": "SYNTHETIC-EPFO-001",
            "obligation_period": "2026-06",
            "expected_members": 2,
            "expected_rows": 6,
            "control_totals": {"INR": "360"},
            "label": "Synthetic eight-field arrears",
            "ecr_arrear_controls": {
                "epf_wages": "1500",
                "eps_wages": "1000",
                "edli_wages": "1500",
                "employee_pf": "180",
                "employer_pf": "97",
                "employer_eps": "83",
            },
            "arrear_context_evidence_version_id": uuid.uuid4(),
            "arrear_disbursement_date": "2026-07-10",
            "arrear_scope_assessment": "Independent retained establishment, wage-month attribution and salary arrear disbursement context assessed for every member",
            **changes,
        }
    )


def parse(content=ARREARS, data=None, country="IN"):
    return parse_native(content, data or options(), country, "SYNTHETIC-arrears.txt")


def test_arrear_field_order_wages_context_and_unverified_payment_are_preserved():
    result = parse()
    rows = result["rows"]
    assert len(rows) == 6 and result["control_totals"] == {"INR": "360"}
    first = {row["component"]: row["amount"] for row in rows if row["source_row"] == 1}
    assert first == {"PF:EMPLOYEE": "120", "PF:EMPLOYER": "37", "PF:EPS": "83"}
    assert all(row["payment_date"] is None and row["period"] == "2026-06" for row in rows)
    assert any(row["amount"] == "0" and row["component"] == "PF:EPS" for row in rows)
    assert result["allowed_source_roles"] == ["return", "reported"]
    metadata = result["native_metadata"]
    assert metadata["arrear_disbursement_date"] == "2026-07-10"
    assert metadata["filing_status"] == "NOT_VERIFIED"
    assert metadata["statutory_rate_validation"] == "NOT_PERFORMED"
    assert metadata["arrear_controls"]["employer_pf"] == "97"
    assert "Gross wages" in metadata["absent_fields"] and "gross_wages" not in rows[0]


@pytest.mark.parametrize(
    "old,new,message",
    [
        (b"#~#120#~#37#~#83", b"#~#120#~#83#~#37", "controls do not agree"),
        (b"#~#120#~#37", b"#~#120.5#~#37", "whole rupees"),
        (b"#~#120#~#37", b"#~#-120#~#37", "whole rupees"),
        (b"100000000002", b"100000000001", "distinct"),
        (b"100000000002", b"000000000000", "non-zero"),
        (b"SYNTHETIC ARREAR ONE", b" ", "display name"),
        (b"#~#1000#~#1000#~#1000", b"#~#1000#~#1001#~#1000", "hierarchy"),
    ],
)
def test_arrear_layout_and_independent_controls_fail_closed(old, new, message):
    with pytest.raises(ValueError, match=message):
        parse(ARREARS.replace(old, new))


def test_monthly_files_wrong_country_and_missing_context_cannot_be_relabelled():
    with pytest.raises(ValueError, match="exactly eight"):
        parse(MONTHLY)
    with pytest.raises(ValueError, match="unavailable"):
        parse(country="AE")
    for changes in (
        {"arrear_context_evidence_version_id": None},
        {"ecr_arrear_controls": None},
        {"arrear_disbursement_date": None},
        {"arrear_scope_assessment": " " * 20},
        {"expected_rows": 7},
    ):
        with pytest.raises(ValidationError):
            options(**changes)
    data = options()
    with pytest.raises(ValidationError):
        options(
            arrear_context_evidence_version_id=data.evidence_version_id,
            evidence_version_id=data.evidence_version_id,
        )
    with pytest.raises(ValidationError):
        options(file_format="india-epfo-ecr")


def test_independent_member_and_component_controls_cannot_be_replaced_by_net_total():
    with pytest.raises(ValueError, match="member count"):
        parse(data=options(expected_members=1, expected_rows=3))
    controls = options().ecr_arrear_controls.model_dump()
    controls.update(employee_pf=Decimal("181"), employer_pf=Decimal("96"))
    with pytest.raises(ValueError, match="controls do not agree"):
        parse(data=options(ecr_arrear_controls=controls))


def test_arrear_member_bound_retains_every_component_without_rounding_or_role_swap():
    lines = [
        f"{100000000000 + index}#~#SYNTHETIC ARREAR {index}#~#1000#~#1000#~#1000#~#120#~#37#~#83"
        for index in range(1666)
    ]
    controls = {
        "epf_wages": "1666000",
        "eps_wages": "1666000",
        "edli_wages": "1666000",
        "employee_pf": "199920",
        "employer_pf": "61642",
        "employer_eps": "138278",
    }
    data = options(
        expected_members=1666,
        expected_rows=4998,
        control_totals={"INR": "399840"},
        ecr_arrear_controls=controls,
    )
    result = parse(("\n".join(lines) + "\n").encode(), data)
    assert result["row_count"] == 4998 and result["control_totals"] == {"INR": "399840"}
    assert result["native_metadata"]["arrear_controls"]["employer_pf"] == "61642"
    with pytest.raises(ValueError, match="1-1,666"):
        parse(("\n".join([*lines, lines[0]]) + "\n").encode(), data)
