"""Read the EPFO monthly eleven-field text profile; never infer filing or payment."""

import calendar
import re
from datetime import date
from decimal import Decimal

from app.modules.country_workflows.schemas import Obligation

ECR_REFERENCE = "https://www.epfindia.nic.in/site_docs/PDFs/MiscPDFs/User-Manual-ReECR_v3.0.pdf"


def whole(value):
    if not re.fullmatch(r"\d{1,12}", value):
        raise ValueError("ECR wage and contribution fields must be unsigned whole rupees")
    return Decimal(value)


def parse_ecr(content, data):
    if (
        not data.obligation_period
        or not data.employer_registration
        or data.expected_members is None
    ):
        raise ValueError(
            "Select the wage month, establishment registration and independent member count"
        )
    try:
        year, month = map(int, data.obligation_period.split("-"))
        date(year, month, 1)
        days = calendar.monthrange(year, month)[1]
        text = content.decode("utf-8-sig")
    except (UnicodeDecodeError, ValueError):
        raise ValueError("ECR requires UTF-8 text and a valid declared wage month") from None
    # Establishment and wage month are selected in EPFO's upload workflow. Neither
    # is contained in the member text; retain their explicit declared basis.
    establishment = data.employer_registration
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9/\-]{2,39}", establishment):
        raise ValueError("Select an explicit establishment registration without whitespace")
    lines = text.splitlines()
    if not lines or len(lines) > 1666:
        raise ValueError("Monthly ECR requires 1–1,666 member lines within the derived-row bound")
    if len(lines) != data.expected_members:
        raise ValueError("ECR independent member-count control does not agree")
    rows, members = [], set()
    wage_totals = {key: Decimal(0) for key in ("gross", "epf", "eps", "edli")}
    contribution_totals = {
        key: Decimal(0) for key in ("employee_pf", "employer_eps", "employer_pf", "advance_refund")
    }
    ncp_total = 0
    for ordinal, line in enumerate(lines, 1):
        fields = line.split("#~#")
        if len(fields) != 11:
            raise ValueError(
                "Monthly ECR must contain exactly eleven #~# separated fields; arrears/legacy layouts are not this profile"
            )
        uan, name, *numbers = fields
        if not re.fullmatch(r"\d{12}", uan) or uan == "0" * 12 or uan in members:
            raise ValueError("ECR member identifiers must be distinct non-zero twelve-digit UANs")
        if not name.strip() or len(name) > 200 or any(ord(ch) < 32 for ch in name):
            raise ValueError("ECR requires a non-empty member name without control characters")
        gross, epf, eps, edli, employee, pension, employer = map(whole, numbers[:7])
        ncp_text, refund_text = numbers[7:]
        if not re.fullmatch(r"\d{1,2}", ncp_text) or int(ncp_text) > days:
            raise ValueError(
                "ECR non-contributory days exceed the selected wage month's calendar days"
            )
        refund = whole(refund_text)
        if epf > gross or eps > epf or edli > epf:
            raise ValueError(
                "ECR wage hierarchy is inconsistent; inspect the original member record"
            )
        members.add(uan)
        ncp_total += int(ncp_text)
        for key, amount in zip(wage_totals, (gross, epf, eps, edli), strict=True):
            wage_totals[key] += amount
        for key, amount in zip(
            contribution_totals, (employee, pension, employer, refund), strict=True
        ):
            contribution_totals[key] += amount
        components = [("PF:EMPLOYEE", employee), ("PF:EPS", pension), ("PF:EMPLOYER", employer)]
        if refund:
            components.append(("PF:ADVANCE_REFUND", refund))
        for component, amount in components:
            row = Obligation(
                id=f"ecr:{ordinal}:{component}",
                registration=establishment,
                subject=uan,
                period=data.obligation_period,
                component=component,
                population="regular",
                currency="INR",
                amount=amount,
                due_date=data.obligation_due_date,
                payment_date=None,
            ).model_dump(mode="json")
            row.update(
                source_row=ordinal,
                gross_wages=str(gross),
                epf_wages=str(epf),
                eps_wages=str(eps),
                edli_wages=str(edli),
                ncp_days=int(ncp_text),
                payment_execution="NOT_EVIDENCED_BY_RETURN_TEXT",
                filing_status="NOT_VERIFIED",
            )
            rows.append(row)
    return rows, {
        "currency": "INR",
        "establishment_registration": establishment,
        "wage_month": data.obligation_period,
        "member_count": len(members),
        "wage_totals": {key: str(value) for key, value in wage_totals.items()},
        "contribution_totals": {key: str(value) for key, value in contribution_totals.items()},
        "ncp_days_total": ncp_total,
        "context_basis": "ESTABLISHMENT_AND_MONTH_DECLARED_SEPARATELY_NOT_PRESENT_IN_TEXT",
        "layout": "EPFO_MONTHLY_11_FIELDS_HASH_TILDE_HASH",
        "control_total_basis": "EMPLOYEE_PF_PLUS_EMPLOYER_EPS_PLUS_EMPLOYER_PF_PLUS_ADVANCE_REFUND",
        "row_grain": "THREE_CONTRIBUTION_ROWS_PER_MEMBER_PLUS_NONZERO_ADVANCE_REFUND",
        "payment_execution": "NOT_EVIDENCED_BY_RETURN_TEXT",
        "filing_status": "NOT_VERIFIED",
        "statutory_rate_validation": "NOT_PERFORMED",
        "membership_and_exemption_validation": "NOT_PERFORMED",
        "due_date_basis": "DECLARED_NOT_LEGALLY_INFERRED",
        "excluded_amounts": [
            "EDLI insurance charges",
            "administration/inspection charges",
            "interest",
            "damages",
            "arrear-return populations",
        ],
        "format_reference": ECR_REFERENCE,
    }
