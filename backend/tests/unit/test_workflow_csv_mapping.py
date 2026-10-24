import uuid
from decimal import Decimal

import pytest

from app.modules.country_workflows.schemas import SourceInput
from app.modules.country_workflows.sources import parse_csv

CONTENT = "رقم;Account;Date;CCY;Signed amount;Description\nROW-1;BANK-1;2026-06-30;AED;100.25;Original export note\n".encode()


def options(**changes):
    return SourceInput(
        **{
            "evidence_version_id": uuid.uuid4(),
            "table_type": "transactions",
            "label": "Synthetic original bank CSV",
            "expected_rows": 1,
            "control_totals": {"AED": "100.25"},
            "delimiter": ";",
            "column_mapping": {
                "id": "رقم",
                "account": "Account",
                "date": "Date",
                "currency": "CCY",
                "amount": "Signed amount",
            },
            "ignored_columns": ["Description"],
            "mapping_rationale": "Description retained in original evidence but excluded from this bounded comparison",
            **changes,
        }
    )


def test_explicit_unicode_headers_mapping_delimiter_controls_and_receipt():
    result = parse_csv(CONTENT, options())
    assert result["rows"][0]["id"] == "ROW-1"
    assert result["rows"][0]["reference"] == ""
    assert result["control_totals"] == {"AED": "100.25"}
    receipt = result["csv_mapping"]
    assert receipt["applied_columns"]["id"] == "رقم"
    assert receipt["ignored_columns"] == ["Description"]
    assert receipt["value_transformations"] == "NONE_TYPED_VALIDATION_ONLY"
    assert "Original export note" not in str(result["rows"])


@pytest.mark.parametrize(
    "changes",
    [
        {"mapping_rationale": ""},
        {"ignored_columns": []},
        {"ignored_columns": ["Description", "Description"]},
        {"ignored_columns": ["Missing"]},
        {"ignored_columns": ["Account", "Description"]},
        {"column_mapping": {"id": "رقم", "amount": "رقم"}},
        {"column_mapping": {"invented_field": "رقم"}},
        {"column_mapping": {"id": "Nonexistent"}},
        {"expected_rows": 2},
        {"control_totals": {"AED": "100.26"}},
    ],
)
def test_mapping_cannot_silently_drop_columns_reuse_values_or_bypass_controls(changes):
    with pytest.raises(ValueError):
        parse_csv(CONTENT, options(**changes))


def test_mapping_does_not_convert_dates_or_absolute_values():
    for old, new in [(b"2026-06-30", b"30/06/2026"), (b"100.25", b"(100.25)")]:
        with pytest.raises(ValueError):
            parse_csv(CONTENT.replace(old, new), options())


def test_native_and_canonical_headers_cannot_compete_for_the_same_target():
    with pytest.raises(ValueError, match="competing"):
        parse_csv(CONTENT.replace(b"Description", b"amount"), options(ignored_columns=[]))


def test_excluded_values_still_obey_raw_row_bounds():
    with pytest.raises(ValueError, match="Invalid CSV row"):
        parse_csv(CONTENT.replace(b"Original export note", b"x" * 4001), options())


def split_options(**changes):
    mapping = {key: value for key, value in options().column_mapping.items() if key != "amount"}
    return options(
        column_mapping=mapping,
        debit_column="Debit",
        credit_column="Credit",
        amount_derivation="debit-positive",
        expected_rows=2,
        control_totals={"AED": "95.25"},
        **changes,
    )


SPLIT = "رقم;Account;Date;CCY;Debit;Credit;Description;reference\nROW-1;BANK-1;2026-06-30;AED;100.25;;Receipt;REF-1\nROW-2;BANK-1;2026-06-30;AED;;5;Payment;REF-2\n".encode()


@pytest.mark.parametrize(
    "mode,total,amounts",
    [
        ("debit-positive", "95.25", ["100.25", "-5"]),
        ("credit-positive", "-95.25", ["-100.25", "5"]),
    ],
)
def test_explicit_debit_credit_sign_conventions_and_original_sides(mode, total, amounts):
    request = split_options().model_copy(
        update={
            "amount_derivation": mode,
            "control_totals": {"AED": Decimal(total)},
        }
    )
    result = parse_csv(SPLIT, request)
    assert [row["amount"] for row in result["rows"]] == amounts
    assert result["rows"][0]["source_debit"] == "100.25"
    assert result["rows"][1]["source_credit"] == "5"
    assert result["csv_mapping"]["amount_derivation"] == mode


@pytest.mark.parametrize(
    "old,new",
    [
        (b"100.25;;", b"100.25;1;"),
        (b"100.25;;", b";;"),
        (b"100.25;;", b"-100.25;;"),
        (b"100.25;;", b"NaN;;"),
        (b"100.25;;", b"1e2;;"),
        (b"100.25;;", b"100,25;;"),
        (b"100.25;;", b"100.123456789;;"),
    ],
)
def test_ambiguous_or_nonplain_debit_credit_values_fail_the_whole_source(old, new):
    with pytest.raises(ValueError):
        parse_csv(SPLIT.replace(old, new), split_options())


@pytest.mark.parametrize(
    "changes",
    [
        {"debit_column": "Credit"},
        {"debit_column": None},
        {"credit_column": None},
        {"table_type": "obligations"},
        {"file_format": "uae-wps-sif"},
        {"mapping_rationale": ""},
    ],
)
def test_derivation_requires_an_explicit_bounded_transaction_profile(changes):
    with pytest.raises(ValueError):
        values = split_options().model_dump()
        SourceInput.model_validate({**values, **changes})


@pytest.mark.parametrize(
    "changes",
    [
        {"ignored_columns": ["Description", "Debit"]},
        {"column_mapping": {**options().column_mapping, "amount": "Debit"}},
        {"debit_column": "Missing"},
    ],
)
def test_derivation_cannot_hide_or_reuse_its_input_columns(changes):
    with pytest.raises(ValueError):
        request = split_options().model_copy(update=changes)
        parse_csv(SPLIT, request)
