"""Deterministic reviewed-input VAT arithmetic; no inferred place-of-supply or legal approval."""

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, localcontext

from app.modules.vat.schemas import Invoice, Rule

D = Decimal
ZERO = D(0)


def money(value):
    return D(value).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def transaction(data: Invoice, rule: Rule, invoice_rule: Rule):
    with localcontext() as ctx:
        ctx.prec = 64
        issues = []
        taxable = data.treatment in {"standard", "reverse_services", "import_goods", "deemed"}
        rate = rule.standard_rate if taxable else ZERO
        if data.tax_rate != rate:
            issues.append("Incorrect tax rate for approved treatment")
        if data.discount > data.amount:
            raise ValueError("Discount exceeds consideration")
        base = data.amount - data.discount
        net_foreign = base / (1 + rate) if data.tax_inclusive else base
        net = money(net_foreign * data.exchange_rate)
        tax = money(net_foreign * rate * data.exchange_rate)
        gross = net + tax
        if data.currency == "AED" and data.exchange_rate != 1:
            issues.append("AED exchange rate must be1")
        if not data.treatment_facts_complete or data.treatment == "unresolved":
            issues.append("Supply classification/place of supply requires documented review")
        if data.tax_point < date(2018, 1, 1):
            issues.append("Pre-UAE-VAT tax point requires historical assessment")
        if data.amount != data.unit_price * data.quantity:
            issues.append("Unit price/quantity differs from consideration")
        if (data.declared_net, data.declared_tax, data.declared_gross) != (net, tax, gross):
            issues.append("Declared AED net/tax/gross does not reconcile")
        reverse = data.treatment in {"reverse_services", "import_goods"}
        if reverse and data.direction != "purchase":
            issues.append("Reverse-charge/import path requires a purchase")
        if data.document_type == "credit_note" and not data.original_invoice_id:
            issues.append("Credit note requires original invoice")
        expected_label = "Tax Credit Note" if data.document_type == "credit_note" else "Tax Invoice"
        if data.document_label != expected_label:
            issues.append("Required tax document label missing")
        if not data.supplier_address or not data.supplier_name:
            issues.append("Supplier identity/address incomplete")
        # Imported supplies are supported by overseas commercial/customs documents, not a fictitious UAE supplier TRN.
        if not reverse and not data.supplier_trn:
            issues.append("Supplier TRN missing")
        simplified = data.invoice_type == "simplified"
        if simplified and (
            reverse or data.customer_registered and gross > invoice_rule.simplified_limit
        ):
            issues.append("Simplified tax invoice not permitted for these facts")
        if (
            not simplified
            and data.customer_registered
            and (not data.customer_name or not data.customer_address or not data.customer_trn)
        ):
            issues.append("Registered recipient details required on full invoice")
        if data.treatment == "reverse_services" and not data.reverse_charge_statement:
            issues.append("Reverse-charge statement/legal basis missing")
        if data.ocr_state == "EXTRACTED_UNVERIFIED":
            issues.append("Extracted document fields require human verification")
        if data.ocr_state == "VERIFIED" and not data.ocr_evidence_id:
            issues.append("Document verification evidence missing; no visual verification inferred")
        sign = D(-1) if data.document_type == "credit_note" else D(1)
        recovery = ZERO
        if data.direction == "purchase" and tax:
            if data.recovery_treatment == "review":
                issues.append("Input recovery assessment unresolved")
            elif data.recovery_treatment != "blocked":
                expected = D(1) if data.recovery_treatment == "full" else data.recovery_percentage
                if data.recovery_treatment == "full" and data.recovery_percentage != 1:
                    issues.append("Full recovery requires100% approved percentage")
                if not data.recovery_evidence_ids:
                    issues.append("Recoverability evidence required")
                recovery = money(tax * expected)
            if data.employee_expense and not data.employee_conditions_confirmed and recovery:
                issues.append("Employee recovery conditions not established")
            if data.tax_point >= date(2026, 10, 1) and recovery:
                small_exception = (
                    net < 10000
                    and data.supplier_annual_past is not None
                    and data.supplier_annual_expected is not None
                    and max(data.supplier_annual_past, data.supplier_annual_expected) <= 100000
                )
                if not small_exception and not data.integrity_review_evidence_id:
                    issues.append("FTA13/2026 supplier/supply integrity evidence missing")
        output = tax if data.direction == "sale" and taxable or reverse else ZERO
        return {
            "net": net * sign,
            "tax": tax * sign,
            "gross": gross * sign,
            "output_vat": output * sign,
            "recoverable_input": recovery * sign,
            "rate": rate,
            "issues": issues,
            "valid": not issues,
            "formula": "AED net=round((consideration-discount)/(1+rate if inclusive else1)*FX,2); VAT=round(unrounded AED net*rate,2); credit note reverses amounts",
            "document_processing": data.ocr_state,
            "legal_qualification_automated": False,
            "execution_mode": "deterministic",
            "classification_reasons": {"treatment": data.treatment,
                "place_of_supply": data.place_of_supply_assessment,
                "rule_key": rule.rule_key, "rule_version": rule.rule_version,
                "facts_reviewed": data.treatment_facts_complete,
                "supply_type": data.supply_type},
        }


def filing_deadline(period_end, holidays):
    due = period_end + timedelta(days=28)
    while due.weekday() >= 5 or due in holidays:
        due += timedelta(days=1)
    return due


def readiness(data, legal_as_of):
    if legal_as_of < date(2026, 5, 14):
        return {
            "state": "REVIEW_REQUIRED",
            "reason": "Historical rollout version requires separate approved dates",
        }
    government = data.government_entity
    large = data.annual_revenue >= 50000000
    appointment = date(2026, 10, 30) if large and not government else date(2027, 3, 31)
    implementation = (
        date(2027, 10, 1) if government else date(2027, 1, 1) if large else date(2027, 7, 1)
    )
    complete = bool(
        data.asp_name
        and data.asp_appointed_on
        and data.asp_appointment_evidence_id
        and data.accreditation_checked_on
        and data.identifiers_complete
        and data.source_mapping_complete
        and data.sandbox_tested
    )
    return {
        "state": "OUTSIDE_ASSESSED_SCOPE"
        if not data.in_scope_b2b_b2g
        else "READINESS_DOCUMENTED"
        if complete
        else "REVIEW_REQUIRED",
        "appointment_due": str(appointment),
        "implementation_due": str(implementation),
        "appointed_on_time": bool(data.asp_appointed_on and data.asp_appointed_on <= appointment),
        "real_asp_connected": False,
        "accreditation": "AuditOS is not an Accredited Service Provider",
        "technical_scope": "Sandbox semantic subset; no full PINT-AE XSD/Schematron certification",
    }
