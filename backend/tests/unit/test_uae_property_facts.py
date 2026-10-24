import pytest
from pydantic import ValidationError
from tests.phase7.test_vat_calculations import invoice


def test_property_vat_requires_facts_before_asserting_complete_treatment():
    with pytest.raises(ValidationError, match="Property VAT"):
        invoice(supply_context="property")
    with pytest.raises(ValidationError, match="Unresolved property"):
        invoice(supply_context="property", treatment_facts_complete=True, property_facts={
            "property_type": "residential", "transaction_nature": "sale", "location": "SYNTHETIC Dubai",
            "contractual_facts": "Synthetic agreement supplied for review",
            "legal_conditions_assessment": "Pending verification of first supply",
            "unresolved_facts": ["First supply date"]})
