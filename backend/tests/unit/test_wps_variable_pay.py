"""Fictional EVP instructions; component detail must never duplicate EDR salary."""

import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.modules.country_workflows.native_sources import parse_native
from app.modules.country_workflows.schemas import WPS_VARIABLE_FIELDS, SourceInput
from tests.unit.native_source_examples import SIF, SIF_FILENAME

EVP = b"EVP,12345678901234,033000000,40.00,10.00,5.00,15.00,20.00,8.00,2.00\n"
SIF_EVP = SIF.replace(b"EDR,12345678901235", EVP + b"EDR,12345678901235")


def options(**changes):
    return SourceInput.model_validate(
        {
            "evidence_version_id": uuid.uuid4(),
            "file_format": "uae-wps-sif-evp",
            "table_type": "obligations",
            "label": "Synthetic variable-pay instructions",
            "expected_rows": 2,
            "control_totals": {"AED": "1500"},
            "wps_variable_pay_count": 1,
            "wps_variable_pay_totals": dict(
                zip(WPS_VARIABLE_FIELDS, ("40", "10", "5", "15", "20", "8", "2"), strict=True)
            ),
            **changes,
        }
    )


def parse(content=SIF_EVP, data=None, country="AE"):
    return parse_native(content, data or options(), country, SIF_FILENAME)


def test_evp_details_preserve_original_records_without_new_obligations():
    result = parse()
    assert result["row_count"] == 2 and result["control_totals"] == {"AED": "1500.00"}
    assert [row["amount"] for row in result["rows"]] == ["1100.00", "400.00"]
    assert [row["source_row"] for row in result["rows"]] == [1, 3]
    assert result["rows"][0]["source_variable_pay_row"] == 2
    assert result["rows"][0]["variable_pay_components"]["housing_allowance"] == "40.00"
    assert "variable_pay_components" not in result["rows"][1]
    assert all(row["payment_date"] is None for row in result["rows"])
    metadata = result["native_metadata"]
    assert metadata["variable_pay_record_count"] == 1 and metadata["employee_count"] == 2
    assert metadata["physical_record_count"] == 4
    assert metadata["payment_execution"] == "NOT_EVIDENCED_BY_INSTRUCTION_FILE"
    assert sum(map(Decimal, metadata["variable_pay_component_totals"].values())) == Decimal("100")


@pytest.mark.parametrize(
    "change, message",
    [
        ("missing", "requires its corresponding EVP"),
        ("orphan", "immediately follow"),
        ("duplicate", "immediately follow"),
        ("wrong-employee", "employee and agent"),
        ("wrong-routing", "employee and agent"),
        ("sum", "component sum"),
        ("negative", "decimal"),
        ("precision", "decimal"),
        ("width", "15-character"),
        ("count", "employee-count"),
        ("salary", "total salary"),
        ("unknown", "orphan or unknown"),
        ("trailer", "final SCR"),
    ],
)
def test_evp_structure_binding_and_double_count_controls(change, message):
    content = SIF_EVP
    if change == "missing":
        content = SIF
    elif change == "orphan":
        content = EVP + SIF
    elif change == "duplicate":
        content = content.replace(EVP, EVP + EVP)
    elif change == "wrong-employee":
        content = content.replace(EVP, EVP.replace(b"12345678901234", b"12345678901235"))
    elif change == "wrong-routing":
        content = content.replace(EVP, EVP.replace(b"033000000", b"033000001"))
    elif change == "sum":
        content = content.replace(b",40.00,10.00", b",41.00,10.00")
    elif change == "negative":
        content = content.replace(b",40.00,10.00", b",-40.00,90.00")
    elif change == "precision":
        content = content.replace(b",40.00,10.00", b",40.000,10.00")
    elif change == "width":
        content = content.replace(b",40.00,10.00", b",0000000000040.00,10.00")
    elif change == "count":
        content = content.replace(b",2,1500.00", b",3,1500.00")
    elif change == "salary":
        content = content.replace(b",2,1500.00", b",2,1600.00")
    elif change == "unknown":
        content = content.replace(b"EVP,", b"XYZ,")
    elif change == "trailer":
        content += content.splitlines(keepends=True)[-1]
    with pytest.raises(ValueError, match=message):
        parse(content)


def test_evp_requires_independent_controls_and_explicit_profile():
    for controls in (
        {"wps_variable_pay_count": None},
        {"wps_variable_pay_totals": {}},
        {"wps_variable_pay_count": True},
    ):
        with pytest.raises(ValidationError):
            options(**controls)
    with pytest.raises(ValueError, match="component-total controls"):
        parse(data=options(wps_variable_pay_count=2))
    controls = options().wps_variable_pay_totals.copy()
    controls["housing_allowance"] = Decimal("41")
    with pytest.raises(ValueError, match="component-total controls"):
        parse(data=options(wps_variable_pay_totals=controls))
    with pytest.raises(ValueError, match="unavailable"):
        parse(country="IN")
    with pytest.raises(ValidationError):
        options(file_format="uae-wps-sif")
    legacy = options().model_copy(
        update={
            "file_format": "uae-wps-sif",
            "wps_variable_pay_count": None,
            "wps_variable_pay_totals": {},
        }
    )
    with pytest.raises(ValueError, match="EDR records"):
        parse(data=legacy)


def test_zero_variable_income_may_have_no_evp_and_requires_explicit_zero_controls():
    content = SIF.replace(b",1000.00,100.00", b",1000.00,0.00").replace(b",1500.00,", b",1400.00,")
    result = parse(
        content,
        options(
            wps_variable_pay_count=0,
            wps_variable_pay_totals=dict.fromkeys(WPS_VARIABLE_FIELDS, "0"),
            control_totals={"AED": "1400"},
        ),
    )
    assert result["native_metadata"]["variable_pay_record_count"] == 0
    assert result["row_count"] == 2


def test_evp_maximum_employee_population_and_physical_record_bound():
    edr = SIF.decode().splitlines()[0].split(",")
    records = []
    for index in range(5000):
        employee = str(10000000000000 + index)
        records.extend(
            [
                ",".join([edr[0], employee, *edr[2:]]),
                f"EVP,{employee},033000000,100.00,0,0,0,0,0,0",
            ]
        )
    records.append(
        "SCR,1234567890123,033000000,2026-06-30,1234,062026,5000,5500000.00,AED,SYNTHETIC"
    )
    controls = dict.fromkeys(WPS_VARIABLE_FIELDS, "0")
    controls["housing_allowance"] = "500000"
    data = options(
        expected_rows=5000,
        control_totals={"AED": "5500000"},
        wps_variable_pay_count=5000,
        wps_variable_pay_totals=controls,
    )
    result = parse(("\n".join(records) + "\n").encode(), data)
    assert (
        result["row_count"] == 5000 and result["native_metadata"]["physical_record_count"] == 10001
    )
    with pytest.raises(ValueError, match="5,000 EDR/EVP pairs"):
        parse(("\n".join(records[:-1] + records[:2] + records[-1:]) + "\n").encode(), data)
