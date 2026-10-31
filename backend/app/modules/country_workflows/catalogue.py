"""Capability states describe implemented scope, not universal legal qualification."""

import json
from collections import Counter
from datetime import date
from pathlib import Path

from app.modules.country_workflows.audit_schemas import AUDIT_WORKFLOWS
from app.modules.country_workflows.diligence_schemas import DILIGENCE_WORKFLOWS
from app.modules.country_workflows.grant_utilisation import ROLES as GRANT_ROLES
from app.modules.country_workflows.merchant_reserves import ROLES as RESERVE_ROLES
from app.modules.country_workflows.msme_interest_schemas import ROLES as MSME_INTEREST_ROLES
from app.modules.country_workflows.msme_schemas import MSME_WORKFLOWS
from app.modules.country_workflows.msme_tax_schemas import ROLES as MSME_TAX_ROLES
from app.modules.country_workflows.operations_schemas import OPERATION_WORKFLOWS
from app.modules.country_workflows.payroll_basis_proration import ROLES as PRORATION_ROLES
from app.modules.country_workflows.payroll_establishment_charges import ROLES as CHARGE_ROLES
from app.modules.country_workflows.payroll_ledger_schemas import PAYROLL_LEDGER_WORKFLOWS
from app.modules.country_workflows.payroll_schemas import PAYROLL_WORKFLOWS
from app.modules.country_workflows.pension_schemas import PENSION_WORKFLOWS
from app.modules.country_workflows.savings_scheme import ROLES as SAVINGS_ROLES
from app.modules.country_workflows.sector_schemas import SECTOR_WORKFLOWS
from app.modules.country_workflows.turnover import ROLES as TURNOVER_ROLES
from app.modules.country_workflows.withholding_schemas import WITHHOLDING_WORKFLOWS
from app.modules.regulatory.tax_forms import india_tax_regime

OPTIONAL_ROLES = {
    "uae-benefit-review": {"service_calendar": "benefit-service-exclusions"},
    "party-balance-confirmations": {"coverage": "confirmation-item-coverage"},
    "expense-cutoff": {
        "recognitions": "cutoff-recognition-lines",
        "postings": "cutoff-posting-lines",
    },
}

WORKFLOWS = {
    "icfr-duty-coverage": (
        "Separately assessed ICFR management / auditor duty and declared-plan coverage",
        ["AE", "IN"],
        {"scopes": "icfr-duty-scopes", "checks": "checks"},
    ),
    "employment-payroll-review": (
        "Assessed employment periods / employee-month controls / corrected payroll register",
        ["AE", "IN"],
        {
            "employment": "employment-payroll-episodes",
            "controls": "employment-payroll-controls",
            "register": "employment-payroll-register",
        },
    ),
    "india-msme-annual-tax": (
        "India assessed MSE annual tax / P&L interest / prior disallowance release",
        ["IN"],
        MSME_TAX_ROLES,
    ),
    "india-msme-interest": (
        "India assessed MSE compound interest / principal changes / interest settlement",
        ["IN"],
        MSME_INTEREST_ROLES,
    ),
    "india-establishment-charges": (
        "India assessed establishment administration / inspection / EDLI charges",
        ["IN"],
        CHARGE_ROLES,
    ),
    "uae-savings-review": (
        "UAE savings-scheme basic contribution and fund statement review",
        ["AE"],
        SAVINGS_ROLES,
    ),
    "india-payroll-basis-proration": (
        "India dated PF wage bases / assessed ceilings / monthly controls",
        ["IN"],
        PRORATION_ROLES,
    ),
    "merchant-reserve-rollforward": (
        "Processor reserve holds / releases / opening-closing / ledger controls",
        ["AE", "IN"],
        RESERVE_ROLES,
    ),
    "merchant-settlement-bridge": (
        "Merchant gross / refunds / fees / net bank settlement",
        ["AE", "IN"],
        {
            "books": "merchant-activity",
            "processor": "merchant-settlements",
            "bank": "transactions",
            "allocations": "merchant-bank-allocations",
        },
    ),
    "tax-turnover-bridge": (
        "Book revenue to VAT/GST turnover by registration and period",
        ["AE", "IN"],
        TURNOVER_ROLES,
    ),
    "grant-utilisation": (
        "Grant mandates / opening utilisation / expenditure allocations",
        [],
        GRANT_ROLES,
    ),
    "inventory-custody-confirmations": (
        "Offsite inventory custody quantities and condition evidence",
        [],
        {
            "positions": "inventory-custody-positions",
            "responses": "inventory-custody-confirmations",
        },
    ),
    "party-balance-confirmations": (
        "Positive customer/vendor balance confirmations",
        [],
        {
            "items": "audit-open-items",
            "controls": "balance-controls",
            "responses": "party-confirmations",
        },
    ),
    "inventory-fifo-cost": (
        "Assessed FIFO opening / receipt / issue / gross book cost roll-forward",
        [],
        {"movements": "inventory-cost-movements", "books": "stock"},
    ),
    "inventory-valuation-control": (
        "Inventory cost / NRV evidence and recorded GL controls",
        [],
        {"books": "stock", "valuations": "inventory-valuations", "controls": "accounting-controls"},
    ),
    "india-esic-population": (
        "India ESIC member, paid-day and wage reconciliation",
        ["IN"],
        {"payroll": "esic-members", "reported": "esic-members"},
    ),
    "india-document-series": (
        "India GSTR-1 document series and cancellation counts",
        ["IN"],
        {"books": "gst-document-series", "reported": "gst-document-series"},
    ),
    "india-gstr1-documents": (
        "India GSTR-1 outward invoice/note reconciliation",
        ["IN"],
        {"books": "tax-documents", "return": "tax-documents"},
    ),
    "india-gstr1-summary": (
        "India GSTR-1 summary metric reconciliation",
        ["IN"],
        {"books": "gst-summary-metrics", "return": "gst-summary-metrics"},
    ),
    **WITHHOLDING_WORKFLOWS,
    **OPERATION_WORKFLOWS,
    **MSME_WORKFLOWS,
    **PAYROLL_WORKFLOWS,
    **PAYROLL_LEDGER_WORKFLOWS,
    **PENSION_WORKFLOWS,
    **AUDIT_WORKFLOWS,
    **DILIGENCE_WORKFLOWS,
    **SECTOR_WORKFLOWS,
    "uae-vat-return": (
        "UAE VAT201 return-box bridge",
        ["AE"],
        {"books": "return-boxes", "return": "return-boxes"},
    ),
    "bank-account-evidence": (
        "Bank account identity and owner evidence",
        ["AE", "IN"],
        {role: "bank-account-evidence" for role in ("register", "ledger", "bank")},
    ),
    "bank-brs": (
        "Account-level bank reconciliation",
        [],
        {"books": "transactions", "statement": "transactions"},
    ),
    "uae-vat": (
        "UAE VAT document reconciliation",
        ["AE"],
        {"books": "tax-documents", "return": "tax-documents"},
    ),
    "india-invoice-register": (
        "India invoice evidence to purchase/sales register",
        ["IN"],
        {"books": "tax-documents", "invoices": "tax-documents"},
    ),
    "india-gst": (
        "India GST document reconciliation",
        ["IN"],
        {"books": "tax-documents", "return": "tax-documents"},
    ),
    "payroll-settlement": (
        "Payroll / payment channel / bank bridge",
        ["AE", "IN"],
        {"payroll": "obligations", "channel": "obligations", "bank": "obligations"},
    ),
    "statutory-dues": (
        "Statutory dues and settlement register",
        ["AE", "IN"],
        {"expected": "obligations", "return": "obligations", "payment": "obligations"},
    ),
    "india-withholding": (
        "Legacy aggregate withholding comparison (legal roles unassessed)",
        ["IN"],
        {"books": "obligations", "return": "obligations", "payment": "obligations"},
    ),
    "stock-audit": (
        "Inventory quantity and valuation evidence",
        [],
        {"books": "stock", "count": "stock"},
    ),
    "controls": ("Internal-control evidence assessment", [], {"checks": "checks"}),
    "vendor-diligence": ("Vendor verification evidence", [], {"checks": "checks"}),
    "nonprofit-diligence": ("Nonprofit eligibility evidence", ["AE", "IN"], {"checks": "checks"}),
    "tax-close": ("Country tax-close evidence checklist", ["AE", "IN"], {"checks": "checks"}),
}

SOURCES = {
    "india-form-transition": "https://www.incometax.gov.in/iec/foportal/help/all-topics/e-filing-services/income-tax-forms?mobile-app=1",
    "india-tcs-withdrawal": "https://www.incometaxindia.gov.in/w/section-72-94",
    "uae-wps": "https://u.ae/en/information-and-services/jobs/employment-in-the-private-sector/payment-of-wages",
    "uae-vat": "https://tax.gov.ae/-/media/Files/EN/PDF/Guides/VAT-Returns-User-Guide.pdf",
}


def country_guidance(country, as_of, tax_year_start=None):
    """Selection guidance only: no invented rate or filing/deadline calculation."""
    if country == "AE":
        return {
            "tax_reporting": "UAE CT/VAT workbenches; Indian tax-audit forms not applicable",
            "payroll": "Assess MOHRE/WPS applicability, exclusions, employment regime and pension cohort",
            "wps_reference": "Resolution 340/2026: confirm operative effective date and scope"
            if as_of.year >= 2026
            else "Select historical WPS resolution applicable to the pay period",
            "excluded_domestic_components": ["PF", "ESI", "PT", "TDS", "TCS"],
            "sources": {k: v for k, v in SOURCES.items() if k.startswith("uae")},
            "legal_status": "SOURCE_GUIDANCE_REQUIRES_ENGAGEMENT_ASSESSMENT",
        }
    if country == "IN":
        return {
            "tax_reporting": "PENDING_TAX_YEAR_START"
            if tax_year_start is None
            else "Form 26 under 2025 Act / 2026 Rules"
            if india_tax_regime(tax_year_start) == "2025-ACT"
            else "Legacy 3CA/3CB/3CD under 1961 Act",
            "form_selection_basis": "Tax-year start, not run date: assess explicitly before issuing a report",
            "tcs_206c_1h": "WITHDRAWN"
            if as_of >= date(2025, 4, 1)
            else "HISTORICAL_REQUIRES_QUALIFIED_RULE",
            "payroll": "Membership continuity, establishment coverage, state PT and pension cohorts required",
            "sources": {k: v for k, v in SOURCES.items() if k.startswith("india")},
            "legal_status": "SOURCE_GUIDANCE_REQUIRES_ENGAGEMENT_ASSESSMENT",
        }
    return {"legal_status": "SHARED_CORE_ONLY", "sources": {}}


def catalogue(country=None):
    return [
        {
            "id": key,
            "title": title,
            "countries": countries,
            "roles": roles,
            "optional_roles": OPTIONAL_ROLES.get(key, {}),
            "available": key != "india-withholding" and (not countries or country in countries),
            "state": "LEGACY_PREVIEW_REQUIRES_ROLE_SCOPED_REPLACEMENT"
            if key == "india-withholding"
            else "EVIDENCE_WORKFLOW",
            "statutory_calculation_qualified": False,
        }
        for key, (title, countries, roles) in WORKFLOWS.items()
    ]


def scenarios():
    return json.loads((Path(__file__).parent / "scenarios.json").read_text(encoding="utf-8"))


def scenario_evidence():
    items = scenarios()
    return {
        "dataset_kind": "SYNTHETIC_ENGINE_FIXTURES",
        "count_basis": "AUTHORED_REFERENCE_SCENARIOS",
        "scenario_count": len(items),
        "counts_by_country": dict(sorted(Counter(item["country"] for item in items).items())),
        "client_validation": "NOT_ESTABLISHED_BY_CATALOGUE",
        "execution_status": "CONSULT_SOURCE_SPECIFIC_TEST_RECEIPTS",
        "statutory_qualification": False,
        "legacy_count_field": "real_world_scenario_count",
        "legacy_count_meaning": "Synthetic reference fixture count, not validated client cases",
    }


def check_templates(country):
    common = {
        "controls": [
            "design-assessment",
            "population-completeness",
            "access-review",
            "operating-effectiveness",
            "deficiency-evaluation",
            "retest",
        ],
        "vendor-diligence": [
            "legal-identity",
            "ownership",
            "bank-ownership",
            "financial-health",
            "conflicts",
            "sanctions-review",
            "registry-verification-status",
        ],
    }
    if country == "AE":
        common.update(
            {
                "nonprofit-diligence": [
                    "legal-identity",
                    "fundraising-permission-scope",
                    "governance",
                    "restricted-fund-utilisation",
                    "financial-statements",
                    "sanctions-review",
                ],
                "tax-close": [
                    "vat-registration-period",
                    "vat201-source-bridge",
                    "ct-applicability",
                    "qfzp-applicability",
                    "audited-statements-applicability",
                    "transfer-pricing-applicability",
                    "tax-group-boundaries",
                ],
            }
        )
    elif country == "IN":
        common.update(
            {
                "nonprofit-diligence": [
                    "legal-identity",
                    "csr-implementing-agency-applicability",
                    "csr1-applicability",
                    "12ab-80g-status",
                    "fcra-applicability",
                    "fund-utilisation",
                    "audited-filings",
                    "governance",
                ],
                "tax-close": [
                    "income-tax-regime-and-form",
                    "gst-registration-periods",
                    "gst-turnover-bridge",
                    "withholding-role-and-year",
                    "tax-audit-applicability",
                    "annual-gst-return-applicability",
                ],
            }
        )
    return common
