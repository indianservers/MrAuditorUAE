from copy import deepcopy

import pytest

from tests.unit.test_shared_audit_workflows import run


def population(currency="AED", sign=-1):
    return {
        "outstanding": [
            {
                "id": "O1",
                "account": "BANK-1",
                "currency": currency,
                "date": "2026-06-20",
                "balance_date": "2026-06-30",
                "reference": "SYN-CHEQUE",
                "amount": str(100 * sign),
                "evidence_reference": "SYN-BRS",
            }
        ],
        "statement": [
            {
                "id": "T1",
                "account": "BANK-1",
                "currency": currency,
                "date": "2026-07-02",
                "reference": "SYN-CLEARING",
                "amount": str(100 * sign),
                "counterparty": "",
            }
        ],
        "allocations": [
            {
                "id": "A1",
                "outstanding_id": "O1",
                "transaction_id": "T1",
                "currency": currency,
                "amount": "40",
                "evidence_reference": "SYN-CLEARING-REVIEW",
                "rationale": "Independently assessed cheque clearing allocation",
            }
        ],
    }


def calculate(p, **changes):
    return run(
        "bank-subsequent-clearance",
        p,
        account="BANK-1",
        currency=p["outstanding"][0]["currency"],
        **changes,
    )


@pytest.mark.parametrize("currency", ["AED", "INR"])
@pytest.mark.parametrize("sign", [-1, 1])
def test_partial_clearance_preserves_reporting_amounts_and_unallocated_cash(currency, sign):
    p = population(currency, sign)
    original = deepcopy(p)
    result = calculate(p)
    assert p == original
    item, statement = result["rows"]
    assert item["reporting_date_amount"] == str(100 * sign)
    assert item["remaining_after_review"] == str(60 * sign)
    assert item["subsequently_cleared"] == "40"
    assert item["state"] == "PARTIALLY_CLEARED"
    assert statement["unallocated_amount"] == "60"
    assert result["reporting_date_population_changed"] is False


def test_full_clearance_and_split_bank_movements():
    p = population()
    p["statement"][0]["amount"] = "-40"
    p["statement"].append({**p["statement"][0], "id": "T2", "amount": "-60"})
    p["allocations"].append(
        {**p["allocations"][0], "id": "A2", "transaction_id": "T2", "amount": "60"}
    )
    result = calculate(p)
    assert result["exception_count"] == 0
    assert result["rows"][0]["remaining_after_review"] == "0"
    assert len(result["rows"][0]["clearances"]) == 2


@pytest.mark.parametrize(
    "role,field,value,error",
    [
        ("outstanding", "account", "OTHER", "account or currency"),
        ("statement", "currency", "USD", "account or currency"),
        ("outstanding", "balance_date", "2026-06-29", "balance date"),
        ("statement", "date", "2026-06-30", "strictly after"),
        ("statement", "date", "2026-09-01", "review window"),
        ("statement", "amount", "100", "signed movement"),
        ("allocations", "amount", "101", "overallocated"),
        ("allocations", "transaction_id", "MISSING", "missing outstanding"),
        ("allocations", "currency", "USD", "allocation currency"),
    ],
)
def test_invalid_clearance_cannot_discharge_reporting_items(role, field, value, error):
    p = population()
    p[role][0][field] = value
    with pytest.raises(ValueError, match=error):
        calculate(p)


def test_duplicate_pair_cannot_double_clear_and_short_window_requires_explicit_scope():
    p = population()
    p["allocations"].append({**p["allocations"][0], "id": "A2"})
    with pytest.raises(ValueError, match="Duplicate outstanding"):
        calculate(p)
    with pytest.raises(ValueError, match="review window"):
        calculate(population(), review_through="2026-06-29")


def test_duplicate_original_item_under_another_id_cannot_inflate_clearance_population():
    p = population()
    p["outstanding"].append({**p["outstanding"][0], "id": "O2"})
    with pytest.raises(ValueError, match="Duplicate outstanding reference"):
        calculate(p)


@pytest.mark.parametrize("currency", ["AED", "INR"])
@pytest.mark.parametrize("sign", [-1, 1])
def test_flagged_reversal_cannot_clear_but_remains_in_statement_population(currency, sign):
    p = population(currency, sign)
    p["statement"][0]["is_reversal"] = True
    with pytest.raises(ValueError, match="reversal bank movement"):
        calculate(p)
    p["allocations"] = []
    result = calculate(p)
    item, statement = result["rows"]
    assert item["remaining_after_review"] == str(100 * sign)
    assert statement["state"] == "REVERSAL_NOT_CLEARANCE"
    assert statement["is_reversal"] is True
    assert statement["statement_amount"] == str(100 * sign)
    assert statement["unallocated_amount"] == "100"
    assert result["exception_count"] == 2


@pytest.mark.parametrize("file_format", ["camt053", "swift-mt940"])
def test_native_statement_reversal_is_not_subsequent_clearance(file_format):
    from datetime import date
    from types import SimpleNamespace

    from app.modules.country_workflows.bank_clearance import clearances
    from app.modules.country_workflows.native_sources import parse_native
    from tests.unit.native_source_examples import CAMT, MT940
    from tests.unit.test_native_workflow_sources import options

    if file_format == "camt053":
        content = CAMT.replace(b"<RvslInd>false</RvslInd>", b"<RvslInd>true</RvslInd>")
    else:
        # Reversal of credit is a debit; preserve the original signed -5 movement.
        content = MT940.replace(b"0602D5,00", b"0602RC5,00")
    native = parse_native(content, options(file_format), "AE", "synthetic.xml" if file_format == "camt053" else "synthetic.mt940")
    reversed_row = next(row for row in native["rows"] if row["is_reversal"])
    p = population()
    p["outstanding"][0].update(date="2026-05-20", balance_date="2026-05-31", amount="-5")
    p["statement"] = native["rows"]
    p["allocations"][0].update(transaction_id=reversed_row["id"], amount="5")
    scope = SimpleNamespace(account="BANK-1", currency="AED", as_of=date(2026, 5, 31), review_through=date(2026, 6, 30))
    with pytest.raises(ValueError, match="reversal bank movement"):
        clearances(scope, p)
