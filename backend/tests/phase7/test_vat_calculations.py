import csv
import io
from datetime import date
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

from app.modules.demo.generator import generate
from app.modules.demo.guard import (
    DEMO_TENANT,
    configuration_guard,
)
from app.modules.demo.guard import (
    test_database_guard as database_guard,
)
from app.modules.vat.calculations import filing_deadline, readiness, transaction
from app.modules.vat.schemas import Invoice, Rule

ID = "00000000-0000-0000-0000-000000000001"


def invoice(**changes):
    raw = generate(0, 2026, 1, 0)["invoices"][0]
    raw.pop("source_ids")
    raw.pop("original_index")
    raw.pop("expected_output")
    raw.pop("expected_input")
    raw.update(
        profile_id=ID, rule_id=ID, invoice_rule_id=ID, net_line_ids=[ID], evidence_record_ids=[ID]
    )
    raw.update(changes)
    return Invoice.model_validate(raw)


def rule(**changes):
    return Rule.model_validate(
        {
            "rule_key": "output",
            "rule_version": 1,
            "category": "output",
            "source_id": "VAT-LAW",
            "article": "3",
            "effective_from": "2018-01-01",
            "known_from": "2018-01-01",
            "source_document_version": "Test",
            "technical_review": "Test",
            "conditions": "Test",
            "exceptions": "Test",
            **changes,
        }
    )


@pytest.mark.parametrize(
    "changes,net,tax",
    [
        ({}, "1000", "50"),
        (
            {"amount": "1050", "unit_price": "1050", "discount": "0", "tax_inclusive": True},
            "1000",
            "50",
        ),
        ({"treatment": "zero", "tax_rate": "0"}, "1000", "0"),
        ({"treatment": "exempt", "tax_rate": "0"}, "1000", "0"),
        ({"treatment": "outside", "tax_rate": "0"}, "1000", "0"),
        (
            {
                "document_type": "credit_note",
                "original_invoice_id": ID,
                "document_label": "Tax Credit Note",
            },
            "-1000",
            "-50",
        ),
        ({"currency": "USD", "exchange_rate": "3.6725"}, "3672.50", "183.63"),
    ],
)
def test_output_categories_inclusive_credit_fx(changes, net, tax):
    result = transaction(invoice(**changes), rule(), rule())
    assert result["net"] == D(net) and result["tax"] == D(tax)


def test_input_recovery_and_no_account_name_inference():
    data = invoice(
        direction="purchase",
        recovery_treatment="partial",
        recovery_percentage="0.4",
        recovery_evidence_ids=[ID],
        integrity_review_evidence_id=ID,
    )
    value = transaction(data, rule(), rule())
    assert value["recoverable_input"] == 20
    blocked = data.model_copy(update={"recovery_treatment": "blocked"})
    assert transaction(blocked, rule(), rule())["recoverable_input"] == 0
    missing = data.model_copy(update={"recovery_evidence_ids": []})
    assert "Recoverability evidence required" in transaction(missing, rule(), rule())["issues"]


def test_invoice_simplified_full_and_missing_facts():
    simplified = invoice(
        invoice_type="simplified",
        customer_registered=False,
        customer_name="",
        customer_address="",
        customer_trn="",
    )
    assert transaction(simplified, rule(), rule())["valid"]
    full = simplified.model_copy(update={"invoice_type": "full", "customer_registered": True})
    assert not transaction(full, rule(), rule())["valid"]
    assert not transaction(
        invoice(treatment="unresolved", treatment_facts_complete=False), rule(), rule()
    )["valid"]
    assert not transaction(invoice(ocr_state="EXTRACTED_UNVERIFIED"), rule(), rule())["valid"]


def test_reverse_charge_and_supplier_integrity_thresholds():
    data = invoice(
        direction="purchase",
        treatment="reverse_services",
        supplier_trn="",
        reverse_charge_statement="Article48",
        recovery_treatment="full",
        recovery_percentage="1",
        recovery_evidence_ids=[ID],
        integrity_review_evidence_id=ID,
    )
    value = transaction(data, rule(), rule())
    assert value["output_vat"] == 50 and value["recoverable_input"] == 50
    no_evidence = data.model_copy(update={"integrity_review_evidence_id": None})
    assert not transaction(no_evidence, rule(), rule())["valid"]
    exception = no_evidence.model_copy(
        update={"supplier_annual_past": D(100000), "supplier_annual_expected": D(100000)}
    )
    assert transaction(exception, rule(), rule())["valid"]
    over = exception.model_copy(update={"supplier_annual_expected": D("100000.01")})
    assert not transaction(over, rule(), rule())["valid"]


def test_deadline_holidays_and_rollout_boundary():
    assert filing_deadline(date(2026, 10, 31), [date(2026, 11, 30)]) == date(2026, 12, 1)
    profile = SimpleNamespace(
        government_entity=False,
        annual_revenue=D(50000000),
        asp_name="",
        asp_appointed_on=None,
        asp_appointment_evidence_id=None,
        accreditation_checked_on=None,
        identifiers_complete=False,
        source_mapping_complete=False,
        sandbox_tested=False,
        in_scope_b2b_b2g=True,
    )
    assert readiness(profile, date(2026, 10, 18))["appointment_due"] == "2026-10-30"
    profile.annual_revenue = D("49999999.99")
    assert readiness(profile, date(2026, 10, 18))["implementation_due"] == "2027-07-01"


def test_demo_guards_and_deterministic_balances():
    config = SimpleNamespace(
        environment="test",
        synthetic_data_enabled=True,
        database_url="postgresql://user@localhost/auditos_phase7_demo",
        demo_database_name="auditos_phase7_demo",
        demo_tenant_id=str(DEMO_TENANT),
    )
    configuration_guard(config)
    for key, value in [
        ("environment", "production"),
        ("synthetic_data_enabled", False),
        ("demo_tenant_id", ID),
        ("demo_database_name", "production"),
    ]:
        bad = SimpleNamespace(**{**vars(config), key: value})
        with pytest.raises(ValueError):
            configuration_guard(bad)
    with pytest.raises(ValueError):
        database_guard(config, "auditos_phase7_demo")
    first = generate(0, 2024, 167)
    assert first["csv"] == generate(0, 2024, 167)["csv"]
    journals = {}
    for row in csv.DictReader(io.StringIO(first["csv"].decode())):
        journals[row["Journal Number"]] = (
            journals.get(row["Journal Number"], D(0)) + D(row["Debit"]) - D(row["Credit"])
        )
    assert all(value == 0 for value in journals.values())
    assert first["rows"] >= 8334 and sum(map(D, first["balances"].values())) == 0
