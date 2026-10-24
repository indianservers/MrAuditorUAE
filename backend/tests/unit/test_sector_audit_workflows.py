from decimal import Decimal

import pytest

from tests.unit.test_shared_audit_workflows import run


def trade_line(**changes):
    return {"id": "T1", "shipment": "SHIP-1", "product": "SKU-1", "counterparty": "V1",
            "currency": "AED", "uom": "unit", "date": "2026-06-10", "quantity": "10",
            "amount": "100", "evidence_reference": "TRADE-EVIDENCE", **changes}


def test_customs_value_adjustment_and_reviewed_duty_rate():
    sources = {"declarations": [trade_line(amount="110", valuation_adjustment="10", declared_duty="5.5",
                                          reviewed_duty_rate="0.05", duty_rule_reference="REVIEWED-RATE")],
               "invoices": [trade_line(id="I1")], "receipts": [trade_line(id="R1")]}
    output = run("customs-reconciliation", sources)
    assert output["exception_count"] == 0 and not output["blocked"]
    sources["declarations"][0]["declared_duty"] = "5"
    assert "DUTY_DIFFERENCE" in run("customs-reconciliation", sources)["rows"][0]["exceptions"]


def test_customs_missing_rule_and_wrong_party_do_not_pass():
    output = run("customs-reconciliation", {
        "declarations": [trade_line()], "invoices": [trade_line(id="I1", counterparty="OTHER")],
        "receipts": [trade_line(id="R1")]
    })
    assert output["blocked"] and len(output["rows"]) == 2


def price(**changes):
    return {"id": "P1", "product": "SKU-1", "currency": "AED", "uom": "unit",
            "effective_from": "2026-01-01", "effective_to": "2026-12-31",
            "minimum_unit_price": "8", "maximum_unit_price": "12",
            "evidence_reference": "LICENSED-REVIEWED-PRICE-SOURCE", **changes}


def test_trade_uses_real_supplied_price_band_not_invented_benchmark():
    sources = {"invoices": [trade_line()], "shipments": [trade_line(id="S1")],
               "payments": [trade_line(id="P1")], "prices": [price()]}
    output = run("trade-document-review", sources)
    assert not output["blocked"] and output["exception_count"] == 0
    sources["prices"] = []
    output = run("trade-document-review", sources)
    assert output["blocked"] and "PRICE_NOT_TESTABLE" in output["rows"][0]["exceptions"]
    sources["prices"] = [price(maximum_unit_price="9")]
    assert "PRICE_OUTSIDE_SOURCED_BAND" in run("trade-document-review", sources)["rows"][0]["exceptions"]


def excise_movement(kind, quantity, **changes):
    return {"id": kind, "product": "SKU-1", "location": "WH-1", "currency": "AED", "uom": "litre",
            "date": "2026-01-01" if kind == "opening" else "2026-06-30", "kind": kind,
            "quantity": quantity, "amount": "100", "evidence_reference": "EXCISE-STOCK", **changes}


def excise_sources():
    return {"movements": [excise_movement("opening", "100"), excise_movement("receipt", "20"),
                          excise_movement("taxable-release", "30"), excise_movement("closing", "90")],
            "rules": [{"id": "RULE-1", "product": "SKU-1", "currency": "AED", "uom": "litre",
                       "effective_from": "2026-01-01", "effective_to": "2026-12-31",
                       "basis": "quantity", "rate": "2", "evidence_reference": "SYNTHETIC-EXCISE-RULE"}],
            "returns": [{"id": "RETURN-1", "product": "SKU-1", "currency": "AED",
                         "period_start": "2026-01-01", "period_end": "2026-06-30", "amount": "60"}]}


def test_excise_stock_conservation_and_reviewed_quantity_tax():
    output = run("excise-reconciliation", excise_sources())
    assert not output["blocked"] and output["exception_count"] == 0
    assert output["rows"][-1]["expected_tax"] == "60"


def test_excise_value_basis_and_stock_or_rule_gap_are_explicit():
    sources = excise_sources()
    sources["rules"][0].update(basis="value", rate="0.6")
    assert run("excise-reconciliation", sources)["exception_count"] == 0
    sources["movements"][-1]["quantity"] = "89"
    assert run("excise-reconciliation", sources)["blocked"]
    sources = excise_sources()
    sources["rules"] = []
    output = run("excise-reconciliation", sources)
    assert output["blocked"]
    assert output["rows"][0]["state"] == "EXCISE_RULE_MISSING_OR_AMBIGUOUS"


def metal(kind, grams, **changes):
    return {"id": kind, "lot": "LOT-1", "location": "WH-1", "kind": kind,
            "date": "2026-01-01" if kind == "opening" else "2026-06-30",
            "gross_grams": grams, "purity": "0.75", "ownership": "owned",
            "evidence_reference": "SYNTHETIC-ASSAY", **changes}


def test_gold_fine_weight_reconciles_and_purity_difference_is_not_hidden():
    sources = {"books": [metal("opening", "100"), metal("receipt", "20"), metal("issue", "10")],
               "counts": [metal("count", "110")]}
    output = run("gold-reconciliation", sources)
    assert output["exception_count"] == 0
    assert Decimal(output["rows"][0]["book_fine_grams"]) == Decimal("82.5")
    sources["counts"][0]["purity"] = "0.74"
    assert run("gold-reconciliation", sources)["rows"][0]["state"] == "METAL_DIFFERENCE"
    sources["counts"][0]["ownership"] = "unconfirmed"
    assert run("gold-reconciliation", sources)["blocked"]


def escrow_entry(**changes):
    return {"id": "B1", "project": "PROJECT-1", "account": "ESCROW-1", "currency": "AED",
            "date": "2026-06-01", "reference": "PAY-1", "counterparty": "CONTRACTOR-1",
            "amount": "-100", "authorisation_id": "AUTH-1", "evidence_reference": "PAYMENT-1", **changes}


def authorisation(**changes):
    return {"id": "AUTH-1", "project": "PROJECT-1", "account": "ESCROW-1", "currency": "AED",
            "beneficiary": "CONTRACTOR-1", "valid_from": "2026-01-01", "valid_to": "2026-12-31",
            "maximum_amount": "100", "authority_reference": "REVIEWED-AUTHORITY",
            "evidence_reference": "APPROVAL-1", **changes}


def test_escrow_authority_caps_are_cumulative_not_per_payment():
    sources = {"books": [escrow_entry()], "bank": [escrow_entry(id="S1")],
               "authorisations": [authorisation()]}
    assert run("escrow-disbursements", sources)["exception_count"] == 0
    sources["books"].append(escrow_entry(id="B2", reference="PAY-2"))
    sources["bank"].append(escrow_entry(id="S2", reference="PAY-2"))
    output = run("escrow-disbursements", sources)
    assert output["blocked"] and output["rows"][0]["state"] == "AUTHORISATION_LIMIT_EXCEEDED"


def test_escrow_wrong_project_cannot_use_another_projects_authorisation():
    output = run("escrow-disbursements", {"books": [escrow_entry()],
                 "bank": [escrow_entry(id="S1")], "authorisations": [authorisation(project="OTHER")]})
    assert output["blocked"] and output["rows"][0]["state"] == "AUTHORISATION_MISSING_OR_OUT_OF_SCOPE"


def test_escrow_distinct_arabic_counterparties_do_not_collapse_to_empty_ascii_names():
    output = run("escrow-disbursements", {"books": [escrow_entry(counterparty="شركة ألف")],
                 "bank": [escrow_entry(id="S1", counterparty="شركة باء")],
                 "authorisations": [authorisation(beneficiary="شركة ألف")]})
    assert output["rows"][-1]["state"] == "BANK_ITEMS_UNRESOLVED"


def billing_line(kind, amount="100", **changes):
    return {"id": kind, "case_id": "CASE-1", "line_reference": "SERVICE-1", "party": "PAYER-1",
            "currency": "AED", "date": "2026-06-01", "kind": kind, "quantity": "2", "amount": amount,
            "unit_tariff": "50", "approved": True, "evidence_reference": "BILLING-EVIDENCE", **changes}


@pytest.mark.parametrize("workflow", ["hospitality-revenue", "healthcare-billing"])
def test_service_invoice_net_settlement_bridge(workflow):
    sources = {"services": [billing_line("service")], "invoices": [billing_line("invoice")],
               "settlements": [billing_line("settlement", "90"), billing_line("commission", "10")]}
    output = run(workflow, sources)
    assert not output["blocked"] and output["exception_count"] == 0
    assert output["rows"][0]["expected_net_settlement"] == "90"
    sources["settlements"][0]["amount"] = "80"
    assert "COLLECTION_DIFFERENCE" in run(workflow, sources)["rows"][0]["exceptions"]


def test_healthcare_tariff_missing_blocks_and_denials_require_follow_up():
    output = run("healthcare-billing", {"services": [billing_line("service", unit_tariff=None)],
        "invoices": [billing_line("invoice")], "settlements": [billing_line("denial")]})
    assert output["blocked"]
    assert {"TARIFF_NOT_TESTABLE", "DENIED_CLAIM_REVIEW", "COLLECTION_DIFFERENCE"} <= set(output["rows"][0]["exceptions"])


def test_construction_reuses_ifrs15_and_compares_retention():
    project = {"id": "PROJECT-1", "currency": "AED", "reporting_date": "2026-06-30",
               "contract_price": "1000", "constrained_variations": "200", "actual_cost": "400",
               "cost_to_complete": "600", "billed_to_date": "500", "recorded_revenue": "480",
               "recorded_retention": "50", "certified_retention": "50",
               "over_time_assessment": "Reviewed supported over-time contract eligibility",
               "variation_evidence": "VARIATION-1", "certificate_evidence": "CERTIFICATE-1"}
    output = run("construction-contracts", {"projects": [project]})
    assert output["calculation_engine"] == "ifrs.revenue"
    assert Decimal(output["rows"][0]["expected_revenue"]) == Decimal("480")
    assert Decimal(output["rows"][0]["contract_liability"]) == Decimal("20")
    assert output["exception_count"] == 0
    project["recorded_retention"] = "51"
    assert "RETENTION_DIFFERENCE" in run("construction-contracts", {"projects": [project]})["rows"][0]["exceptions"]
