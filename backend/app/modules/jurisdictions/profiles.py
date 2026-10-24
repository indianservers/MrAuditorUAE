"""Typed configuration profiles. Applicability candidates require professional review."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.modules.jurisdictions.packages import package


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Source(Strict):
    id: str
    title: str
    url: HttpUrl
    checked_on: date = date(2026, 10, 24)


class Rule(Strict):
    id: str
    category: str
    source_ids: list[str]
    effective_from: date | None = None
    effective_to: date | None = None
    required_attributes: list[str] = Field(
        default_factory=lambda: [
            "entity_type",
            "reporting_framework",
            "financial_period",
            "professional_applicability_review",
        ]
    )
    readiness: Literal["REVIEW_REQUIRED", "PLANNED"] = "REVIEW_REQUIRED"

    @model_validator(mode="after")
    def valid_dates(self):
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("Rule effective dates are reversed")
        return self


class JurisdictionProfile(Strict):
    country: str = Field(pattern="^[A-Z]{2}$")
    version: str
    name: str
    status: Literal["CONFIGURED_PROFILE", "BASE_PROFILE"]
    currencies: list[str]
    financial_year: str
    accounting_standards: list[str]
    auditing_standards: list[str]
    tax_categories: list[str]
    reporting_requirements: list[str]
    disclosure_templates: list[str]
    materiality_methodology: str
    chart_mappings: str
    risk_rules: list[str]
    module_availability: dict[str, str]
    sources: list[Source]
    rules: list[Rule]
    entity_types: list[str]
    document_templates: list[str]
    legal_effectivity: str = "Candidate configuration only; effective-dated applicability must be reviewed against primary sources. No automatic statutory opinion."

    @model_validator(mode="after")
    def source_integrity(self):
        ids = {source.id for source in self.sources}
        if any(not set(rule.source_ids) <= ids for rule in self.rules):
            raise ValueError("Unknown regulatory source")
        if any(len(c) != 3 or not c.isupper() for c in self.currencies):
            raise ValueError("Currency must be an uppercase ISO code")
        return self


class ApplicabilityDecision(Strict):
    rule_id: str
    applies: bool
    effective_from: date
    effective_to: date | None = None
    source_ids: list[str] = Field(min_length=1)
    rationale: str = Field(min_length=10, max_length=4000)

    @model_validator(mode="after")
    def period_order(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("Applicability dates are reversed")
        return self


def resolve_rules(config, as_of, entity_type, decisions=()):
    by_id = {d.rule_id: d for d in decisions}
    result = []
    for rule in config.rules:
        decision = by_id.get(rule.id)
        start = decision.effective_from if decision else rule.effective_from
        end = decision.effective_to if decision else rule.effective_to
        status = "REQUIRES_PROFESSIONAL_REVIEW"
        if entity_type not in config.entity_types:
            status = "ENTITY_TYPE_UNRESOLVED"
        elif start and (as_of < start or (end and as_of > end)):
            status = "OUTSIDE_EFFECTIVE_PERIOD"
        elif decision:
            status = "REVIEWED_APPLICABLE" if decision.applies else "REVIEWED_NOT_APPLICABLE"
        result.append(
            {
                "rule_id": rule.id,
                "category": rule.category,
                "status": status,
                "as_of": as_of.isoformat(),
                "source_ids": decision.source_ids if decision else rule.source_ids,
                "engine": config.module_availability.get(rule.category, "PLANNED"),
            }
        )
    return result


def profile(country):
    base = package(country)
    special = country in {"AE", "IN"}
    india = country == "IN"
    tax = (
        ["GST", "TDS", "TCS", "Income Tax", "Tax Audit / Form 3CD"]
        if india
        else ["Corporate Tax", "VAT", "QFZP", "Transfer Pricing", "DMTT"]
        if country == "AE"
        else []
    )
    sources = (
        [
            Source(
                id="mca",
                title="MCA Schedule III notification (source, not a consolidated current rule set)",
                url="https://www.mca.gov.in/Ministry/pdf/NotificationScheduleIII_12102018.pdf",
            ),
            Source(
                id="icai",
                title="ICAI auditing and assurance standards",
                url="https://www.icai.org/post/auditing-and-assurance-standards",
            ),
            Source(
                id="income-tax", title="Income Tax Department", url="https://www.incometax.gov.in/"
            ),
            Source(id="gst", title="GST Council", url="https://gstcouncil.gov.in/"),
        ]
        if india
        else [
            Source(
                id="mof",
                title="UAE Ministry of Finance financial legislation",
                url="https://mof.gov.ae/en/financial-legislation/",
            ),
            Source(
                id="fta",
                title="FTA Corporate Tax guidance",
                url="https://www.tax.gov.ae/en/taxes/corporate.tax/faqs.aspx",
            ),
        ]
        if country == "AE"
        else []
    )
    return JurisdictionProfile(
        country=country,
        version=f"{country}-profile-2026.10.24",
        name=base["name"],
        status="CONFIGURED_PROFILE" if special else "BASE_PROFILE",
        currencies=[
            {
                "IN": "INR",
                "AE": "AED",
                "GB": "GBP",
                "US": "USD",
                "SG": "SGD",
                "SA": "SAR",
                "AU": "AUD",
            }.get(country, base.get("currency_default"))
        ]
        if country in {"IN", "AE", "GB", "US", "SG", "SA", "AU"} or base.get("currency_default")
        else [],
        financial_year="April–March default; confirm entity-specific legal period"
        if india
        else "Entity-specific; confirm registration and approved period",
        accounting_standards=["Ind AS", "Applicable AS"]
        if india
        else ["IFRS", "Applicable reporting framework"]
        if country == "AE"
        else ["Requires entity-specific configuration"],
        auditing_standards=["ICAI Standards on Auditing"]
        if india
        else ["ISA-based methodology; confirm engagement applicability"]
        if country == "AE"
        else ["Requires local standard selection"],
        tax_categories=tax,
        reporting_requirements=[
            "Companies Act reporting",
            "Schedule III",
            "CARO (subject to applicability)",
        ]
        if india
        else ["IFRS reporting", "Consolidation and governance", "Corporate tax and VAT review"]
        if country == "AE"
        else [],
        disclosure_templates=[
            "Existing shared working-paper template; statutory templates planned"
        ],
        materiality_methodology="Existing versioned benchmark/percentage workflow with documented professional judgement; no country-prescribed percentage inferred",
        chart_mappings="Entity-specific versioned account mappings; no automatic country reclassification",
        risk_rules=["Shared risk assessment and source-linked findings"],
        module_availability={name: "PLANNED" if india else "EXISTING_SCOPED" for name in tax},
        sources=sources,
        rules=[
            Rule(
                id=f"{country}-{index}",
                category=name,
                source_ids=[s.id for s in sources],
                readiness="PLANNED" if india else "REVIEW_REQUIRED",
            )
            for index, name in enumerate(tax)
        ],
        entity_types=["company", "partnership", "branch", "other"],
        document_templates=[
            "Shared audit planning",
            "Shared working papers",
            "Shared evidence requests",
        ],
    )
