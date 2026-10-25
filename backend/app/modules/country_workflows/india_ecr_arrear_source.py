"""Read explicit EPFO ECR 2.0 arrears; never infer original month, filing or payment."""

import re
from datetime import date
from decimal import Decimal

from app.modules.country_workflows.india_ecr_source import whole
from app.modules.country_workflows.schemas import Obligation

REFERENCE = "https://www.epfindia.gov.in/site_docs/PDFs/EPFOUnifiedPortal/Introduction_ECR2.0.pdf"


def parse_arrears(content, data):
    try:
        date.fromisoformat(data.obligation_period + "-01")
        text = content.decode("utf-8-sig")
    except (UnicodeDecodeError, ValueError, TypeError):
        raise ValueError("Arrear ECR requires UTF-8 text and a valid declared wage month") from None
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9/\-]{2,39}", data.employer_registration):
        raise ValueError("Select an explicit arrear establishment registration without whitespace")
    lines = text.splitlines()
    if not 1 <= len(lines) <= 1666 or len(lines) != data.expected_members:
        raise ValueError(
            "Arrear ECR requires 1-1,666 member lines matching the independent member count"
        )
    totals = {
        key: Decimal(0)
        for key in (
            "epf_wages",
            "eps_wages",
            "edli_wages",
            "employee_pf",
            "employer_pf",
            "employer_eps",
        )
    }
    rows, members = [], set()
    for ordinal, line in enumerate(lines, 1):
        fields = line.split("#~#")
        if len(fields) != 8:
            raise ValueError(
                "Arrear ECR must contain exactly eight #~# separated fields; monthly and legacy layouts are different profiles"
            )
        uan, name, *numbers = fields
        if not re.fullmatch(r"[0-9]{12}", uan) or uan == "0" * 12 or uan in members:
            raise ValueError("Arrear ECR needs distinct non-zero twelve-digit UANs")
        if not name.strip() or len(name) > 200 or any(ord(ch) < 32 for ch in name):
            raise ValueError(
                "Arrear ECR requires a non-empty display name without control characters"
            )
        epf, eps, edli, employee, employer, pension = map(whole, numbers)
        if eps > epf or edli > epf:
            raise ValueError("Arrear ECR wage hierarchy is inconsistent")
        members.add(uan)
        for key, amount in zip(totals, (epf, eps, edli, employee, employer, pension), strict=True):
            totals[key] += amount
        for component, amount in (
            ("PF:EMPLOYEE", employee),
            ("PF:EPS", pension),
            ("PF:EMPLOYER", employer),
        ):
            row = Obligation(
                id=f"ecr-arrear:{ordinal}:{component}",
                registration=data.employer_registration,
                subject=uan,
                period=data.obligation_period,
                component=component,
                population="arrears",
                currency="INR",
                amount=amount,
                due_date=data.obligation_due_date,
                payment_date=None,
            ).model_dump(mode="json")
            rows.append(
                {
                    **row,
                    "source_row": ordinal,
                    "return_population": "ARREAR_ONLY",
                    "arrear_epf_wages": str(epf),
                    "arrear_eps_wages": str(eps),
                    "arrear_edli_wages": str(edli),
                    "arrear_disbursement_date": data.arrear_disbursement_date.isoformat(),
                    "period_basis": "DECLARED_RETAINED_CONTEXT_NOT_PRESENT_IN_MEMBER_TEXT",
                    "payment_execution": "NOT_EVIDENCED_BY_RETURN_TEXT",
                    "filing_status": "NOT_VERIFIED",
                }
            )
    if totals != data.ecr_arrear_controls.model_dump():
        raise ValueError("Independent arrear wage and contribution controls do not agree")
    return rows, {
        "currency": "INR",
        "layout": "EPFO_ECR2_ARREAR_8_FIELDS_HASH_TILDE_HASH",
        "establishment_registration": data.employer_registration,
        "wage_month": data.obligation_period,
        "member_count": len(members),
        "arrear_controls": {key: str(value) for key, value in totals.items()},
        "arrear_context_evidence_version_id": str(data.arrear_context_evidence_version_id),
        "arrear_disbursement_date": data.arrear_disbursement_date.isoformat(),
        "scope_assessment": data.arrear_scope_assessment.strip(),
        "context_basis": "ESTABLISHMENT_MONTH_AND_DISBURSEMENT_DECLARED_FROM_SEPARATE_RETAINED_CONTEXT",
        "row_grain": "THREE_ARREAR_CONTRIBUTION_ROWS_PER_MEMBER_INCLUDING_ZERO_COMPONENTS",
        "employer_field_basis": "FIELD_7_EMPLOYER_EPF_IS_SEPARATE_FROM_FIELD_8_PENSION_NOT_GROSS_EMPLOYER_CONTRIBUTION",
        "payment_execution": "NOT_EVIDENCED_BY_RETURN_TEXT",
        "filing_status": "NOT_VERIFIED",
        "statutory_rate_validation": "NOT_PERFORMED",
        "membership_and_exemption_validation": "NOT_PERFORMED",
        "due_date_basis": "DECLARED_NOT_LEGALLY_INFERRED_FROM_DISBURSEMENT",
        "absent_fields": ["Gross wages", "NCP days", "Advance refunds"],
        "excluded_amounts": [
            "Monthly return populations",
            "EDLI insurance charges",
            "Administration/inspection charges",
            "Interest",
            "Damages",
        ],
        "format_reference": REFERENCE,
    }
