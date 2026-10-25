"""Literal account identity expectations; no bank or registry authentication."""

import uuid
from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.modules.country_workflows.bank_accounts import BankAccountEvidence, owner_name
from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.schemas import SourceInput, WorkflowInput
from app.modules.country_workflows.sources import parse_csv
from tests.qa_crud.test_country_workflows import csv_bytes
from tests.unit.native_source_examples import iban


def population(country="AE"):
    row = dict(
        id="R1",
        account="SYN-BANK",
        bank_country=country,
        account_scheme="IBAN" if country == "AE" else "LOCAL",
        account_number=iban() if country == "AE" else "000123456789",
        routing_code="033" if country == "AE" else "SYNB0ABC123",
        currency="AED" if country == "AE" else "INR",
        owner_country=country,
        owner_name="SYNTHETIC Entity LLC",
        owner_identifier_scheme="SYNTHETIC-REGISTRY",
        owner_identifier="00123",
        valid_from="2026-01-01",
        valid_through="2026-12-31",
        assertion_status="confirmed",
        evidence_reference="SYNTHETIC independent evidence",
        assessment="Synthetic independently assessed account ownership assertion",
    )
    return {
        role: [{**row, "id": role + "-1", "evidence_reference": "SYNTHETIC-" + role}]
        for role in ("register", "ledger", "bank")
    }


def parameters(country="AE", **changes):
    return WorkflowInput(
        **{
            **dict(
                workflow="bank-account-evidence",
                source_ids={role: uuid.uuid4() for role in ("register", "ledger", "bank")},
                as_of="2026-06-30",
                title="SYNTHETIC bank account review",
                rationale="Independent synthetic bank account scope controls",
                account="SYN-BANK",
                currency="AED" if country == "AE" else "INR",
                bank_owner_name="SYNTHETIC Entity LLC",
                bank_owner_identifier_scheme="SYNTHETIC-REGISTRY",
                bank_owner_identifier="00123",
            ),
            **changes,
        }
    )


def run(rows=None, country="AE", **changes):
    rows = deepcopy(rows or population(country))
    sources = {}
    for role, pop in rows.items():
        inputs = SourceInput(
            evidence_version_id=uuid.uuid4(),
            table_type="bank-account-evidence",
            label="SYNTHETIC account " + role,
            expected_rows=len(pop),
            control_totals={},
        )
        sources[role] = parse_csv(csv_bytes(pop), inputs)
    return calculate(parameters(country, **changes), country, sources)


@pytest.mark.parametrize("country", ["AE", "IN"])
def test_three_independent_scopes_match_without_asserting_bank_authentication(country):
    result = run(country=country)
    assert not result["blocked"] and result["exception_count"] == 0
    assert len(result["rows"]) == 3
    assert result["bank_authentication_status"] == "NOT_ESTABLISHED_BY_DOCUMENT_COMPARISON"
    assert result["bank_account_scope"]["owner_identifier"] == "00123"
    assert set(result["bank_profile_references"]) == {country}


@pytest.mark.parametrize(
    "field,value,issue",
    [
        ("account_number", "AE000331234567890123456", "UAE_IBAN_CHECK_DIGITS_INVALID"),
        ("account_number", "AE１２３", "UAE_IBAN_FORMAT_UNRESOLVED"),
        ("account_scheme", "LOCAL", "UAE_IBAN_FORMAT_UNRESOLVED"),
        ("routing_code", "999", "UAE_BANK_CODE_DIFFERS_FROM_IBAN"),
        ("owner_identifier", "123", "OWNER_IDENTIFIER_UNRESOLVED"),
        ("owner_identifier_scheme", "OTHER-REGISTRY", "OWNER_IDENTIFIER_SCHEME_UNRESOLVED"),
        ("owner_name", "Unrelated Entity LLC", "OWNER_NAME_UNRESOLVED"),
        ("owner_name", "", "OWNER_NAME_UNRESOLVED"),
        ("owner_country", "IN", "OWNER_COUNTRY_DIFFERS_FROM_ENGAGEMENT"),
        ("currency", "USD", "ACCOUNT_CURRENCY_DIFFERS_FROM_SCOPE"),
        ("assertion_status", "unconfirmed", "ACCOUNT_ASSERTION_NOT_CONFIRMED"),
        ("assertion_status", "closed", "ACCOUNT_ASSERTION_NOT_CONFIRMED"),
        ("valid_from", "2026-07-01", "ACCOUNT_EVIDENCE_OUTSIDE_VALIDITY"),
        ("valid_through", "2026-05-31", "ACCOUNT_EVIDENCE_OUTSIDE_VALIDITY"),
        ("bank_country", "GB", "BANK_COUNTRY_PROFILE_NOT_SUPPORTED"),
    ],
)
def test_mismatched_or_unqualified_bank_assertion_blocks_approval(field, value, issue):
    rows = population()
    rows["bank"][0][field] = value
    result = run(rows)
    assert result["blocked"]
    assert issue in result["rows"][2]["exceptions"]


@pytest.mark.parametrize(
    "routing", ["SYNB1ABC123", "SYNB0ABC12", "12340ABC123", "SYNB0ＡＢＣ123", "ſYNB0ABC123"]
)
def test_india_ifsc_is_separate_from_uae_iban(routing):
    rows = population("IN")
    rows["ledger"][0]["routing_code"] = routing
    result = run(rows, "IN")
    assert "INDIA_IFSC_FORMAT_UNRESOLVED" in result["rows"][1]["exceptions"]
    assert result["blocked"]


def test_shared_normalization_preserves_account_and_owner_leading_zeros():
    rows = population("IN")
    rows["bank"][0].update(account_number="123456789", owner_identifier="123")
    result = run(rows, "IN")
    assert result["blocked"]
    assert "ACCOUNT_NUMBER_DIFFERS_FROM_REGISTER" in result["rows"][2]["exceptions"]
    assert "OWNER_IDENTIFIER_UNRESOLVED" in result["rows"][2]["exceptions"]
    assert owner_name(" شركة  مثال ") == owner_name("شركة مثال")
    assert owner_name("Example Ltd") != owner_name("Example Limited")


def test_printed_iban_case_and_spaces_are_only_representation_normalization():
    rows = population()
    value = rows["bank"][0]["account_number"]
    rows["bank"][0]["account_number"] = " ".join(
        value[i : i + 4] for i in range(0, len(value), 4)
    ).lower()
    assert not run(rows)["blocked"]


@pytest.mark.parametrize("role", ["register", "ledger", "bank"])
def test_missing_duplicate_and_wrong_account_populations_are_not_selected_implicitly(role):
    rows = population()
    rows[role].append({**rows[role][0], "id": "SECOND"})
    with pytest.raises(ValueError, match="exactly one"):
        run(rows)
    rows = population()
    rows[role][0]["account"] = "OTHER"
    with pytest.raises(ValueError, match="scope differs"):
        run(rows)


def test_owner_scope_and_validity_are_required_and_only_apply_to_this_workflow():
    with pytest.raises(ValidationError, match="explicit owner"):
        parameters(bank_owner_identifier=" ")
    row = population()["bank"][0]
    with pytest.raises(ValidationError, match="ordered"):
        BankAccountEvidence.model_validate({**row, "valid_from": "2027-01-01"})
    with pytest.raises(ValidationError, match="only to bank account"):
        parameters(workflow="controls", source_ids={"checks": uuid.uuid4()})


def test_foreign_uae_bank_account_of_indian_entity_uses_bank_country_profile():
    rows = population()
    for source in rows.values():
        source[0]["owner_country"] = "IN"
    result = run(rows, "IN", currency="AED")
    assert not result["blocked"]
    assert set(result["bank_profile_references"]) == {"AE"}
