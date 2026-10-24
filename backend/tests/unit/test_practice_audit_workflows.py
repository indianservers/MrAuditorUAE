from decimal import Decimal

import pytest

from tests.unit.test_shared_audit_workflows import control, item, run


def rate(**changes):
    return {
        "id": "RATE-1",
        "min_overdue_days": 0,
        "max_overdue_days": 36500,
        "weighted_loss_rate": "0.1",
        "effective_from": "2026-01-01",
        "effective_to": "2026-12-31",
        "evidence_reference": "REVIEWED-RATE-1",
        "methodology": "Auditor-reviewed probability weighted loss rate",
        **changes,
    }


def test_ecl_uses_existing_engine_on_gl_controlled_exposures():
    output = run("receivables-ecl", {"items": [item()], "controls": [control()], "rates": [rate()]})
    assert not output["blocked"]
    assert Decimal(output["total_ecl_by_currency"]["AED"]) == Decimal("10")
    assert output["calculation_engine"] == "ifrs.ecl/provision_matrix"
    assert output["rows"][-1]["overdue_days"] == 30


@pytest.mark.parametrize(
    "rates,state",
    [
        ([], "RATE_MISSING"),
        ([rate(effective_to="2026-05-31")], "RATE_MISSING"),
        ([rate(), rate(id="RATE-2")], "AMBIGUOUS_RATE"),
    ],
)
def test_ecl_missing_or_overlapping_rate_blocks_review(rates, state):
    output = run("receivables-ecl", {"items": [item()], "controls": [control()], "rates": rates})
    assert output["blocked"] and output["rows"][-1]["state"] == state
    assert output["total_ecl_by_currency"] == {}


def test_ecl_never_offsets_unallocated_credit_notes():
    credit = item()
    credit.update(amount="-100", document_type="credit-note")
    output = run(
        "receivables-ecl",
        {"items": [credit], "controls": [control(amount="-100")], "rates": [rate()]},
    )
    assert output["blocked"] and output["rows"][-1]["state"] == "CREDIT_ALLOCATION_REQUIRED"


def forecast(**changes):
    return {
        "id": "F1",
        "scenario": "stress",
        "currency": "AED",
        "date": "2026-08-31",
        "opening_cash": "100",
        "inflows": "10",
        "outflows": "150",
        "committed_funding": "20",
        "funding_evidence": "FACILITY-1",
        "minimum_cash": "0",
        "assumptions_reference": "FORECAST-ASSUMPTIONS",
        **changes,
    }


def test_cash_forecast_identifies_funding_gap_without_netting_currencies():
    output = run(
        "going-concern-cash", {"forecast": [forecast(), forecast(id="F2", currency="USD")]}
    )
    assert len(output["rows"]) == 2
    assert all(r["funding_gap"] == "20" for r in output["rows"])
    assert all(r["state"] == "EXCEPTIONS" for r in output["rows"])


def test_cash_cannot_reset_to_inconsistent_opening_and_missing_funding_blocks():
    output = run(
        "going-concern-cash",
        {
            "forecast": [
                forecast(date="2026-07-31"),
                forecast(id="F2", opening_cash="1000", funding_evidence=""),
            ]
        },
    )
    assert output["blocked"]
    assert output["rows"][-1]["recalculated_closing"] == "-140"
    assert "OPENING_CASH_BRIDGE_DIFFERENCE" in output["rows"][-1]["exceptions"]
    assert "FUNDING_EVIDENCE_MISSING" in output["rows"][-1]["exceptions"]


def test_forecast_missing_horizon_cannot_pass():
    output = run("going-concern-cash", {"forecast": [forecast(date="2026-07-31")]})
    assert output["blocked"]
    assert output["rows"][-1]["state"] == "FORECAST_HORIZON_MISSING"


def purchase(role, **changes):
    return {
        "id": role,
        "order_id": "PO-1",
        "line_reference": "LINE-1",
        "vendor": "V1",
        "currency": "AED",
        "date": "2026-06-01",
        "document_type": role,
        "quantity": "2",
        "unit_price": "50",
        "amount": "100",
        "evidence_reference": role.upper() + "-DOCUMENT",
        **changes,
    }


def purchases():
    return {
        role: [purchase(kind)]
        for role, kind in {
            "orders": "order",
            "receipts": "receipt",
            "invoices": "invoice",
            "payments": "payment",
        }.items()
    }


def test_three_way_purchase_and_payment_match():
    output = run("procurement-match", purchases())
    assert not output["blocked"] and output["exception_count"] == 0


@pytest.mark.parametrize(
    "changes,exception",
    [
        ({"amount": "110"}, "EXTENSION_DIFFERENCE_INVOICES"),
        ({"quantity": "3", "amount": "150"}, "INVOICE_EXCEEDS_RECEIPT"),
        ({"unit_price": "60", "amount": "120"}, "PRICE_DIFFERENCE"),
    ],
)
def test_procurement_price_quantity_extension_tests(changes, exception):
    sources = purchases()
    sources["invoices"] = [purchase("invoice", **changes)]
    output = run("procurement-match", sources)
    assert exception in output["rows"][0]["exceptions"]


def test_wrong_vendor_does_not_match_purchase_order():
    sources = purchases()
    sources["invoices"] = [purchase("invoice", vendor="OTHER")]
    output = run("procurement-match", sources)
    assert output["blocked"] and len(output["rows"]) == 2


def test_shared_bank_hash_respects_effective_dates():
    common = {
        "bank_account_hash": "a" * 64,
        "effective_from": "2026-01-01",
        "evidence_reference": "MASTER-1",
    }
    output = run(
        "vendor-employee-conflicts",
        {
            "vendors": [{"id": "V1", **common}],
            "employees": [
                {"id": "E1", **common},
                {"id": "E2", **common, "effective_to": "2026-05-31"},
            ],
        },
    )
    assert output["rows"][0]["employee_ids"] == ["E1"]
    assert output["rows"][0]["state"] == "SHARED_BANK_ACCOUNT"


def test_receipt_reuse_and_policy_limit_and_approval_are_independent_signals():
    base = {
        "employee": "E1",
        "currency": "AED",
        "date": "2026-06-01",
        "amount": "101",
        "approved_limit": "100",
        "receipt_sha256": "a" * 64,
        "approved": False,
        "policy_reference": "POLICY-1",
        "evidence_reference": "RECEIPT-1",
    }
    output = run("employee-expenses", {"claims": [{"id": "C1", **base}, {"id": "C2", **base}]})
    assert output["rows"][0]["related_claim_ids"] == ["C2"]
    assert set(output["rows"][0]["exceptions"]) == {
        "POLICY_LIMIT_EXCEEDED",
        "APPROVAL_MISSING",
        "REUSED_RECEIPT",
    }


def benefit_employee(**changes):
    return {
        "id": "E1",
        "regime": "SYNTHETIC-REGIME",
        "currency": "AED",
        "service_start": "2025-07-01",
        "service_end": "2026-06-30",
        "excluded_service_days": 0,
        "monthly_basic_salary": "3000",
        "amount": "2100",
        "scheme": "gratuity",
        "contract_evidence": "CONTRACT-1",
        **changes,
    }


def benefit_rule(**changes):
    return {
        "id": "RULE-1",
        "regime": "SYNTHETIC-REGIME",
        "effective_from": "2026-01-01",
        "effective_to": "2026-12-31",
        "minimum_service_years": "1",
        "year_days": "365",
        "salary_divisor": "30",
        "first_tier_years": "5",
        "first_tier_days": "21",
        "later_tier_days": "30",
        "maximum_salary_months": "24",
        "evidence_reference": "REVIEWED-SYNTHETIC-RULE",
        **changes,
    }


def test_benefits_are_computed_from_reviewed_parameters_not_a_hardcoded_law():
    output = run(
        "uae-benefit-review", {"employees": [benefit_employee()], "rules": [benefit_rule()]}
    )
    assert output["rows"][0]["eligible_service_days"] == 365
    assert Decimal(output["rows"][0]["expected_benefit"]) == Decimal("2100")
    assert output["rows"][0]["state"] == "MATCHED"
    assert output["statutory_calculation_qualified"] is False


def test_benefit_eligibility_and_cap_are_applied():
    output = run(
        "uae-benefit-review",
        {
            "employees": [benefit_employee(excluded_service_days=1, amount="0")],
            "rules": [benefit_rule()],
        },
    )
    assert output["rows"][0]["expected_benefit"] == "0.00"
    output = run(
        "uae-benefit-review",
        {
            "employees": [benefit_employee(amount="300")],
            "rules": [benefit_rule(maximum_salary_months="0.1")],
        },
    )
    assert output["rows"][0]["expected_benefit"] == "300.00"


@pytest.mark.parametrize(
    "employees,rules,state",
    [
        ([benefit_employee()], [], "RULE_MISSING"),
        ([benefit_employee()], [benefit_rule(), benefit_rule(id="RULE-2")], "AMBIGUOUS_RULE"),
        (
            [benefit_employee(scheme="alternative")],
            [benefit_rule()],
            "ALTERNATIVE_SCHEME_REQUIRES_ASSESSMENT",
        ),
    ],
)
def test_unqualified_benefit_regimes_block_approval(employees, rules, state):
    output = run("uae-benefit-review", {"employees": employees, "rules": rules})
    assert output["blocked"] and output["rows"][0]["state"] == state


def test_asset_register_reuses_ifrs_and_gl_and_requires_verification_evidence():
    register = {
        "id": "A1",
        "reference": "ASSET-1",
        "account": "PPE",
        "currency": "AED",
        "cost": "1000",
        "residual": "0",
        "capitalisation_date": "2026-01-01",
        "useful_life_years": "1",
        "method": "straight_line",
        "recorded_depreciation": "1000",
        "recorded_carrying": "0",
        "physical_evidence": "COUNT-1",
        "ownership_evidence": "TITLE-1",
    }
    sources = {
        "register": [register],
        "controls": [
            {
                "id": "GL-1",
                "account": "PPE",
                "currency": "AED",
                "as_of": "2026-12-31",
                "amount": "0",
            }
        ],
    }
    output = run("asset-register-review", sources, as_of="2026-12-31")
    assert output["calculation_engine"] == "ifrs.fixed_assets"
    assert output["exception_count"] == 0
    assert Decimal(output["rows"][-1]["expected_depreciation"]) == 1000
    register["physical_evidence"] = ""
    assert run("asset-register-review", sources, as_of="2026-12-31")["blocked"]


def test_stock_count_bridge_reuses_inventory_without_claiming_reporting_date_attendance():
    stock = {
        "id": "BOOK-1",
        "site": "WH-1",
        "sku": "SKU-1",
        "uom": "unit",
        "currency": "AED",
        "quantity": "10",
        "unit_cost": "10",
        "unit_nrv": "10",
        "ownership": "owned",
        "condition": "good",
        "count_date": "2026-06-30",
    }
    sources = {
        "books": [stock],
        "counts": [{**stock, "id": "COUNT-1", "quantity": "9", "count_date": "2026-06-29"}],
        "movements": [
            {
                "id": "MOVE-1",
                "site": "WH-1",
                "sku": "SKU-1",
                "uom": "unit",
                "currency": "AED",
                "date": "2026-06-30",
                "quantity": "1",
                "evidence_reference": "GRN-1",
            }
        ],
    }
    output = run("inventory-count-bridge", sources)
    assert output["exception_count"] == 0
    assert output["count_bridges"][0]["original_count_date"] == "2026-06-29"
    assert output["count_bridges"][0]["movement_quantity"] == "1"
    sources["movements"][0]["date"] = "2026-06-29"
    with pytest.raises(ValueError, match="outside its count"):
        run("inventory-count-bridge", sources)
