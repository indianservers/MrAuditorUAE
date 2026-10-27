"""Gross misstatements keep explicit currencies; unknown units are not inferred."""

from decimal import Decimal, localcontext


def misstatement_register(records):
    selected = [
        record
        for record in records
        if record.kind == "findings" and record.body.get("finding_type") == "misstatement"
    ]
    totals: dict[str, dict[str, Decimal]] = {}
    unquantified, unassessed = [], []
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        for record in selected:
            amount = record.body.get("financial_impact")
            currency = record.body.get("financial_impact_currency")
            if amount is None:
                unquantified.append(str(record.id))
            if currency is None:
                unassessed.append(str(record.id))
            if amount is None or currency is None:
                continue
            group = totals.setdefault(
                currency, {"corrected_gross": Decimal(0), "uncorrected_gross": Decimal(0)}
            )
            key = (
                "corrected_gross"
                if record.body.get("correction_status") == "corrected"
                else "uncorrected_gross"
            )
            group[key] += abs(Decimal(str(amount)))
    known = {
        currency: {key: str(value) for key, value in amounts.items()}
        for currency, amounts in sorted(totals.items())
    }
    single = (
        next(iter(known.values()))
        if len(known) == 1 and not unquantified and not unassessed
        else None
    )
    return {
        "corrected_gross": single["corrected_gross"] if single else "0" if not selected else None,
        "uncorrected_gross": single["uncorrected_gross"]
        if single
        else "0"
        if not selected
        else None,
        "summary_currency": next(iter(known)) if single else None,
        "totals_by_currency": known,
        "unquantified_ids": sorted(unquantified),
        "unassessed_currency_ids": sorted(unassessed),
        "amount_basis": "GROSS_ABSOLUTE_BY_EXPLICIT_CURRENCY_QUANTIFIED_ITEMS_ONLY",
        "qualitative_review": "Amounts do not determine reporting implications; qualified assessment required",
    }
