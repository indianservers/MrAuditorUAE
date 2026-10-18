"""Deterministic balanced transactions; expected VAT is generated without VAT engine imports."""

import csv
import io
import random
import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

VERSION = "phase7-v1"
CLIENTS = [
    "Al Noor Trading LLC",
    "Emirates Tech Solutions LLC",
    "Gulf Horizon Properties LLC",
    "Desert Logistics FZCO",
    "Crescent Manufacturing LLC",
    "Pearl Hospitality LLC",
    "Falcon Consulting LLC",
    "BlueWave International FZCO",
    "Meridian Investment Holding LLC",
    "Oasis Retail LLC",
]
ACCOUNTS = {
    "100": "Cash",
    "101": "Bank",
    "110": "Trade receivables",
    "120": "Inventory",
    "130": "Prepayments",
    "140": "Property plant and equipment",
    "141": "Accumulated depreciation",
    "150": "Right of use assets",
    "160": "Investment property",
    "170": "Intercompany receivables",
    "180": "Recoverable VAT",
    "200": "Trade payables",
    "210": "Accruals",
    "220": "Lease liabilities",
    "230": "Borrowings",
    "240": "Output VAT",
    "250": "Intercompany payables",
    "300": "Share capital",
    "310": "Retained earnings",
    "400": "Sales revenue",
    "500": "Cost of sales",
    "510": "Payroll",
    "520": "Operating expenses",
    "530": "Finance costs",
    "540": "Tax expense",
}


def identifier(value):
    return uuid.uuid5(uuid.NAMESPACE_URL, "auditos-synthetic/" + VERSION + "/" + value)


def generate(client_index, year, count, minimum_lines=8334):
    rng = random.Random(17000 + client_index * 10 + year)
    records = []
    invoices = []
    expected_output = Decimal(0)
    expected_input = Decimal(0)
    balances = {code: Decimal(0) for code in ACCOUNTS}

    def journal(reference, day, legs, opening=False):
        assert sum((Decimal(d) - Decimal(c) for _, d, c in legs), Decimal(0)) == 0
        ids = {}
        for n, (code, debit, credit) in enumerate(legs):
            source = f"{year}-{reference}-{n}"
            records.append(
                [
                    code,
                    ACCOUNTS[code],
                    reference,
                    str(day),
                    str(debit),
                    str(credit),
                    source,
                    str(opening).lower(),
                    "false",
                    "SYNTHETIC " + reference,
                ]
            )
            balances[code] += Decimal(debit) - Decimal(credit)
            ids[code] = source
        return ids

    journal("OPEN", date(year, 1, 1), [("101", "1000000", "0"), ("300", "0", "1000000")], True)
    first_sale = None
    for i in range(count):
        treatment = [
            "standard",
            "standard",
            "zero",
            "exempt",
            "outside",
            "import_goods",
            "reverse_services",
            "standard",
            "standard",
            "standard",
        ][i % 10]
        direction = (
            "purchase"
            if treatment in {"import_goods", "reverse_services"} or i % 10 in {1, 9}
            else "sale"
        )
        credit = i % 10 == 8 and first_sale is not None
        foreign = i % 10 == 7
        fx = Decimal("3.6725") if foreign else Decimal(1)
        inclusive = i % 10 == 1
        nominal = Decimal("100") if credit else Decimal(1000 + 10 * (i % 20))
        discount = Decimal(10) if i % 17 == 0 and not credit else Decimal(0)
        rate = (
            Decimal("0.05")
            if treatment in {"standard", "import_goods", "reverse_services"}
            else Decimal(0)
        )
        amount = nominal * (1 + rate) + discount if inclusive else nominal + discount
        net = (nominal * fx).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        tax = (nominal * fx * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        gross = net + tax
        sign = Decimal(-1) if credit else Decimal(1)
        ref = f"INV-{year}-{i:04d}"
        day = date(year, 10, 1 + i % 28)
        if direction == "sale":
            legs = [("110", gross, 0), ("400", 0, net)] + ([("240", 0, tax)] if tax else [])
            output, recovered = tax, Decimal(0)
        elif treatment in {"import_goods", "reverse_services"}:
            legs = [("500", net, 0), ("180", tax, 0), ("240", 0, tax), ("200", 0, net)]
            output, recovered = tax, tax
        else:
            legs = [("500", net, 0), ("180", tax, 0), ("200", 0, gross)]
            output, recovered = Decimal(0), tax
        if credit:
            legs = [(code, c, d) for code, d, c in legs]
        sources = journal(ref, day, legs)
        expected_output += output * sign
        expected_input += recovered * sign
        inv = {
            "invoice_number": ref,
            "sequence": i + 1,
            "issue_date": str(day),
            "supply_date": str(day),
            "tax_point": str(day),
            "tax_point_basis": "Synthetic single supply date; accrual basis, no earlier payment",
            "direction": direction,
            "document_type": "credit_note" if credit else "invoice",
            "document_label": "Tax Credit Note" if credit else "Tax Invoice",
            "invoice_type": "full",
            "supplier_name": f"SYNTHETIC {'Overseas' if treatment in {'import_goods', 'reverse_services'} else 'Local'} Supplier {client_index}",
            "supplier_address": "Synthetic test address UAE",
            "supplier_trn": "999999999999999"
            if treatment not in {"import_goods", "reverse_services"}
            else "",
            "supplier_jurisdiction": "GB"
            if treatment in {"import_goods", "reverse_services"}
            else "AE",
            "customer_name": "SYNTHETIC buyer",
            "customer_address": "Synthetic test address",
            "customer_trn": "999999999999998",
            "customer_registered": True,
            "customer_jurisdiction": "AE",
            "description": "Synthetic commercial transaction for testing only",
            "unit_price": str(amount),
            "quantity": "1",
            "amount": str(amount),
            "discount": str(discount),
            "tax_inclusive": inclusive,
            "currency": "USD" if foreign else "AED",
            "exchange_rate": str(fx),
            "exchange_rate_source": "Synthetic deterministic FX fixture; nonproduction test value",
            "treatment": treatment,
            "tax_rate": str(rate),
            "declared_net": str(net),
            "declared_tax": str(tax),
            "declared_gross": str(gross),
            "emirate": ["Dubai", "Abu Dhabi", "Sharjah"][client_index % 3],
            "place_of_supply_assessment": "Synthetic reviewed place-of-supply facts; zero rating not inferred from foreign counterparty",
            "treatment_facts_complete": True,
            "reverse_charge_statement": "Recipient accounts under VAT Law Article48"
            if treatment == "reverse_services"
            else "",
            "recovery_treatment": "full" if direction == "purchase" else "blocked",
            "recovery_percentage": "1" if direction == "purchase" else "0",
            "recovery_basis": "Synthetic business use and recovery conditions independently reviewed",
            "related_party": i % 31 == 0,
            "paid_amount": str(net / 2),
            "original_index": first_sale if credit else None,
            "source_ids": sources,
            "expected_output": str(output * sign),
            "expected_input": str(recovered * sign),
        }
        if direction == "sale" and not credit and treatment == "standard" and first_sale is None:
            first_sale = i
        invoices.append(inv)
    # Cash transfers provide scale without independent random tax/financial totals or artificial profit.
    n = 0
    while len(records) < minimum_lines:
        value = Decimal(rng.randrange(10, 100))
        debit, credit_code = ("100", "101") if n % 2 == 0 else ("101", "100")
        journal(
            f"CASH-{n:05d}",
            date(year, 1 + n % 12, 1 + n % 28),
            [(debit, value, 0), (credit_code, 0, value)],
        )
        n += 1
    stream = io.StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        [
            "Account Code",
            "Account Name",
            "Journal Number",
            "Posting Date",
            "Debit",
            "Credit",
            "Source ID",
            "Opening",
            "Manual",
            "Narration",
        ]
    )
    writer.writerows(records)
    total_debit = sum((Decimal(row[4]) for row in records), Decimal(0))
    credit_total = sum((Decimal(row[5]) for row in records), Decimal(0))
    assert total_debit == credit_total and sum(balances.values(), Decimal(0)) == 0
    return {
        "csv": stream.getvalue().encode(),
        "rows": len(records),
        "debit": str(total_debit),
        "credit": str(credit_total),
        "invoices": invoices,
        "expected_output": str(expected_output),
        "expected_input": str(expected_input),
        "expected_net_vat": str(expected_output - expected_input),
        "balances": {k: str(v) for k, v in balances.items()},
    }
