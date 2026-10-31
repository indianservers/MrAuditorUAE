"""Internal India company-reporting candidates; not a published workflow or opinion.

The retained-source, engagement and independent-adoption adapter is still required.
Unknown facts never become zero or an exemption. Distinct duties remain separate.
"""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from app.modules.jurisdictions.profiles import Strict

Money = Annotated[Decimal, Field(max_digits=28, decimal_places=8, allow_inf_nan=False)]
Nonnegative = Annotated[Money, Field(ge=0)]
Truth = bool | None
CRORE = Decimal("10000000")


def every(*values: Truth) -> Truth:
    return False if False in values else None if None in values else True


def either(*values: Truth) -> Truth:
    return True if True in values else None if None in values else False


def inverse(value: Truth) -> Truth:
    return None if value is None else not value


def within(value: Decimal | None, maximum: Decimal, *, strict=False) -> Truth:
    return None if value is None else value < maximum if strict else value <= maximum


class CompanyFacts(Strict):
    country: Literal["IN"]
    entity_reference: str = Field(min_length=1, max_length=200)
    financial_period_start: date
    financial_period_end: date
    report_date: date
    is_indian_company: Truth
    is_foreign_company: Truth
    is_private_company: Truth
    is_public_company: Truth
    banking_company: Truth
    insurance_company: Truth
    section8_company: Truth
    one_person_company: Truth
    holding_or_subsidiary: Truth
    holding_or_subsidiary_of_public_company: Truth
    governed_by_special_act: Truth
    other_special_exemption_claimed: Truth
    # Immediately preceding FY turnover is deliberately separate from the
    # current-year revenue and latest audited turnover used by other tests.
    small_paid_up_capital: Nonnegative | None
    preceding_financial_year_turnover: Nonnegative | None
    caro_capital_reserves_and_surplus: Money | None
    caro_max_bank_fi_borrowings: Nonnegative | None
    caro_current_year_total_revenue: Nonnegative | None
    latest_audited_turnover: Nonnegative | None
    max_bank_fi_body_corporate_borrowings: Nonnegative | None
    financial_statements_filing_default: Truth
    annual_return_filing_default: Truth
    statement_scope: Literal["standalone", "consolidated"]
    facts_assessment: str = Field(min_length=10, max_length=4000)

    @field_validator(
        "small_paid_up_capital",
        "preceding_financial_year_turnover",
        "caro_capital_reserves_and_surplus",
        "caro_max_bank_fi_borrowings",
        "caro_current_year_total_revenue",
        "latest_audited_turnover",
        "max_bank_fi_body_corporate_borrowings",
        mode="before",
    )
    @classmethod
    def exact_money(cls, value):
        if isinstance(value, (float, bool)):
            raise ValueError("Supply exact decimal strings or integer INR amounts")
        return value

    @model_validator(mode="after")
    def coherent(self):
        if (
            self.financial_period_end < self.financial_period_start
            or self.report_date < self.financial_period_end
        ):
            raise ValueError("Reporting dates must follow the financial period")
        if self.report_date > date.today():
            raise ValueError("A future report date requires a separately assessed forecast scope")
        if self.is_indian_company is True and self.is_foreign_company is True:
            raise ValueError("Indian incorporation and foreign-company status conflict")
        if self.is_private_company is True and self.is_public_company is True:
            raise ValueError("Private and public company status conflict")
        if self.one_person_company is True and (
            self.is_private_company is False or self.is_public_company is True
        ):
            raise ValueError("One Person Company classification conflicts with company status")
        if (
            self.holding_or_subsidiary_of_public_company is True
            and self.holding_or_subsidiary is False
        ):
            raise ValueError("Public group relationship contradicts the broader group facts")
        if len(self.facts_assessment.strip()) < 10 or not self.entity_reference.strip():
            raise ValueError("Retain explicit assessed entity and company facts")
        return self


def evaluate_company_scope(payload):
    """Evaluate candidate scope only; source adoption cannot be asserted by payload."""
    facts = CompanyFacts.model_validate(payload)
    company = either(facts.is_indian_company, facts.is_foreign_company)
    public = False if facts.is_private_company is True else facts.is_public_company
    small_structure = every(
        facts.is_indian_company,
        inverse(public),
        inverse(facts.holding_or_subsidiary),
        inverse(facts.section8_company),
        inverse(facts.governed_by_special_act),
    )
    # Earlier prescribed definitions require their own retained amendment chain.
    current_small_definition = facts.financial_period_end >= date(2025, 12, 1)
    small_money = (
        None
        if not current_small_definition
        else every(
            within(facts.small_paid_up_capital, 10 * CRORE),
            within(facts.preceding_financial_year_turnover, 100 * CRORE),
        )
    )
    small = every(small_structure, small_money)
    private_caro_exemption = every(
        facts.is_indian_company,
        facts.is_private_company,
        inverse(facts.holding_or_subsidiary_of_public_company),
        within(facts.caro_capital_reserves_and_surplus, CRORE),
        within(facts.caro_max_bank_fi_borrowings, CRORE),
        within(facts.caro_current_year_total_revenue, 10 * CRORE),
    )
    caro_exemption = either(
        facts.banking_company,
        facts.insurance_company,
        facts.section8_company,
        facts.one_person_company,
        small,
        private_caro_exemption,
    )
    caro = every(company, inverse(caro_exemption))
    reasons = []
    if facts.financial_period_start < date(2021, 4, 1):
        caro = None
        reasons.append(
            "Earlier financial years require their own CARO commencement/version assessment"
        )
    if small_structure is not False and facts.financial_period_end < date(2025, 12, 1):
        reasons.append("Earlier small-company prescribed limits have not been adopted by this core")
    # S.O.2218(E) corrects the original G.S.R.583(E) 'or' to 'and'.
    financial_ifc_exemption = every(
        within(facts.latest_audited_turnover, 50 * CRORE, strict=True),
        within(facts.max_bank_fi_body_corporate_borrowings, 25 * CRORE, strict=True),
    )
    filing_compliant = every(
        inverse(facts.financial_statements_filing_default),
        inverse(facts.annual_return_filing_default),
    )
    private_ifc_exemption = every(
        facts.is_private_company,
        filing_compliant,
        either(facts.one_person_company, small, financial_ifc_exemption),
    )
    ifc = every(facts.is_indian_company, inverse(private_ifc_exemption))
    section139 = facts.is_indian_company
    if facts.is_foreign_company is True:
        section139 = ifc = None
        reasons.append("Foreign-company audit and IFC reporting require their separate rule chain")
    if facts.financial_period_start < date(2021, 4, 1):
        ifc = section139 = None
        reasons.append("Historical company-audit/IFC transitions are outside this candidate core")
    if facts.other_special_exemption_claimed is not False:
        section139 = ifc = caro = None
        reasons.append(
            "Resolve any other exemption or special statutory regime before using these candidates"
        )
    if facts.governed_by_special_act is not False:
        section139 = ifc = None
        reasons.append("Special-Act audit and IFC requirements need independently adopted rules")
    if facts.banking_company is True or facts.insurance_company is True:
        section139 = ifc = None
        reasons.append(
            "Regulated banking/insurance audit and IFC requirements need their own adopted regime"
        )
    candidates = {
        "small_company": small,
        "companies_act_section139_audit": section139,
        "caro2020_applies": caro,
        "caro_full_standalone_matters": every(caro, facts.statement_scope == "standalone"),
        "caro_consolidated_paragraph3_xxi": every(caro, facts.statement_scope == "consolidated"),
        "section143_3_i_ifc_reporting": ifc,
    }
    return {
        "contract": "india-company-reporting-candidate-core/1",
        "implementation_stage": "INTERNAL_CORE_NOT_EXPOSED_AS_WORKFLOW",
        "entity_reference": facts.entity_reference,
        "country": "IN",
        "candidates": candidates,
        "pending_candidates": [key for key, value in candidates.items() if value is None],
        "basis": {
            "small_company_definition_date": facts.financial_period_end.isoformat(),
            "small_company_capital_limit_inr": str(10 * CRORE)
            if current_small_definition
            else None,
            "small_company_preceding_year_turnover_limit_inr": str(100 * CRORE)
            if current_small_definition
            else None,
            "caro_private_exemption": private_caro_exemption,
            "ifc_financial_exemption_both_tests": financial_ifc_exemption,
            "filing_compliant_as_assessed": filing_compliant,
            "ifc_conjunction_source": "S.O.2218(E), 13 July 2017 corrigendum to G.S.R.583(E)",
        },
        "reasons": reasons,
        "source_binding_verified": False,
        "independent_legal_adoption_verified": False,
        "ready_for_statutory_issue": False,
        "professional_conclusion": "NOT_DETERMINED",
        "limitations": [
            "Candidate company scope only: no tax-audit, LLP, licensing or all-sector exemption conclusion",
            "Missing facts remain unknown; a true statutory audit candidate does not establish audit completion",
            "AS/Ind AS, Schedule III division, report clauses, opinion and authorized issuance remain separate",
            "Original-file binding, engagement scope, legal adoption, independent review and staleness adapter remain unimplemented for this core",
        ],
    }
