"""Authored fictional UAE operating scenarios; no production calculation imports.

Expected amounts below are declared arithmetic, not snapshots of engine output.
All parties, employees, registrations, evidence and bank accounts are fictional.
"""

from copy import deepcopy


def operating_cases():
    cases = []

    def add(workflow, title, sources, expected, arithmetic, **parameters):
        cases.append(
            {
                "id": f"SYN-UAE-{len(cases) + 1:03}",
                "country": "AE",
                "title": "SYNTHETIC UAE " + title,
                "workflow": workflow,
                "sources": deepcopy(sources),
                "expected": expected,
                "parameters": parameters,
                "arithmetic_basis": arithmetic,
                "fixture_family": "FICTIONAL_OPERATING_PILOT",
            }
        )

    def tx(identifier, reference, amount, day="2026-06-25", **changes):
        return {
            "id": identifier,
            "account": "SYN-OPERATING-AED",
            "reference": reference,
            "date": day,
            "currency": "AED",
            "amount": amount,
            "counterparty": "SYNTHETIC Al Noor Gulf Trading LLC",
            **changes,
        }

    bank = {
        "account": "SYN-OPERATING-AED",
        "currency": "AED",
        "book_opening": "250000.00",
        "statement_opening": "250000.00",
        "book_closing": "236750.00",
        "statement_closing": "255395.00",
    }
    books = [
        tx("GL1", "SYN-RECEIPT-106", "126000.00"),
        tx("GL2", "SYN-VENDOR-225", "-52500.00"),
        tx("GL3", "SYN-CHEQUE-801", "-18750.00"),
        tx("GL4", "SYN-PAYROLL-06", "-68000.00"),
    ]
    statement = [dict(r, id="ST-" + r["id"]) for r in books if r["id"] != "GL3"]
    statement.append(tx("ST-FEE", "SYN-BANK-FEE", "-105.00"))
    add(
        "bank-brs",
        "June close with uncleared cheque and unbooked bank fee",
        {"books": books, "statement": statement},
        {
            "exceptions": 2,
            "blocked": False,
            "assertions": [
                {"path": ["matches"], "length": 3},
                {"path": ["adjusted_book_balance"], "decimal_equals": "255395.00"},
                {
                    "path": ["control_comparison", "unexplained_bridge_residual"],
                    "decimal_equals": "0",
                },
            ],
        },
        "Books: 250000+126000-52500-18750-68000=236750. Bank: 250000+126000-52500-68000-105=255395. Adjusted books: 236750+18750-105=255395.",
        **bank,
    )
    corrected = [r for r in books if r["id"] != "GL3"] + [tx("GL-FEE", "SYN-BANK-FEE", "-105.00")]
    add(
        "bank-brs",
        "separately corrected cashbook agrees to bank",
        {"books": corrected, "statement": statement},
        {
            "exceptions": 0,
            "blocked": False,
            "assertions": [{"path": ["matches"], "length": 4}],
        },
        "The separate corrected population excludes the unpresented item and records the 105 fee. Both movement totals are 5395; four unique references agree.",
        **{**bank, "book_closing": "255395.00"},
    )
    old_books = [
        tx("GL-OLD", "SYN-CHEQUE-702", "-18750.00", "2026-02-02"),
        tx("GL-IN", "SYN-RECEIPT-107", "42000.00"),
    ]
    add(
        "bank-brs",
        "aged unpresented cheque remains visible",
        {"books": old_books, "statement": [tx("ST-IN", "SYN-RECEIPT-107", "42000.00")]},
        {
            "exceptions": 1,
            "blocked": False,
            "stale": True,
            "assertions": [{"path": ["adjusted_book_balance"], "decimal_equals": "292000.00"}],
        },
        "250000-18750+42000=273250; add back the uncleared 18750 to reach bank 292000. February 2 is more than 90 days before June 30.",
        **{**bank, "book_closing": "273250.00", "statement_closing": "292000.00"},
    )
    add(
        "bank-brs",
        "foreign currency cannot clear AED operating account",
        {
            "books": [tx("GL-AED", "SYN-FX-1", "42000.00")],
            "statement": [tx("ST-USD", "SYN-FX-1", "42000.00", currency="USD")],
        },
        {"error": "single selected account and currency"},
        "Equal nominal numbers do not permit cross-currency matching. This is an expected rejection.",
        **{**bank, "book_closing": "292000.00", "statement_closing": "292000.00"},
    )

    def invoice(identifier, reference, net, tax, kind="invoice"):
        return {
            "id": identifier,
            "registration": "SYN-TRN-ALNOOR",
            "counterparty": "SYN-CUSTOMER-CEDAR",
            "reference": reference,
            "period": "2026-06",
            "date": "2026-06-20",
            "currency": "AED",
            "document_type": kind,
            "net": net,
            "tax": tax,
            "component": "VAT",
            "status": "active",
        }

    invoices = [
        invoice("INV1", "SYN-INV-0601", "48000.00", "2400.00"),
        invoice("INV2", "SYN-INV-0602", "12500.00", "625.00"),
        invoice("CN1", "SYN-CN-001", "-2500.00", "-125.00", "credit-note"),
    ]
    reported = [dict(r, id="SCHEDULE-" + r["id"]) for r in invoices]
    add(
        "uae-vat",
        "invoices and credit note reconcile separately",
        {"books": invoices, "return": reported},
        {
            "exceptions": 0,
            "blocked": False,
            "assertions": [{"path": ["rows"], "length": 3}],
        },
        "Private prepared schedules, not a UAE supplier portal. Net: 48000+12500-2500=58000. VAT: 2400+625-125=2900. Credit note remains a distinct signed document.",
    )
    changed = deepcopy(reported)
    changed[1]["tax"] = "600.00"
    add(
        "uae-vat",
        "equal taxable base with a 25 dirham tax discrepancy",
        {"books": invoices, "return": changed},
        {
            "exceptions": 1,
            "blocked": False,
            "rows_match": [
                {
                    "reference": "SYN-INV-0602",
                    "state": "VARIANCE",
                    "tax_difference": "25.00",
                }
            ],
        },
        "Second invoice VAT 625 less prepared schedule 600 = 25. Equal net amounts cannot remove the tax variance.",
    )
    add(
        "uae-vat",
        "missing credit note is not netted into invoices",
        {"books": invoices, "return": reported[:2]},
        {
            "exceptions": 1,
            "blocked": False,
            "rows_match": [{"reference": "SYN-CN-001", "state": "BOOKS_ONLY"}],
        },
        "Books contain a separate credit note with net -2500 and VAT -125; its absence from the prepared schedule remains one exception.",
    )

    def box(identifier, number, taxable, tax):
        return {
            "id": identifier,
            "registration": "SYN-TRN-ALNOOR",
            "period_start": "2026-04-01",
            "period_end": "2026-06-30",
            "box": number,
            "currency": "AED",
            "taxable_amount": taxable,
            "tax": tax,
            "adjustment": "0.00",
        }

    allocations = [
        box("B1", "1:DXB", "48000.00", "2400.00"),
        box("B2", "1:DXB", "10000.00", "500.00"),
        box("B3", "10", "5000.00", "250.00"),
    ]
    add(
        "uae-vat-return",
        "declared VAT201 boxes tie without treating them as a full filing",
        {
            "books": allocations,
            "return": [
                box("R1", "1:DXB", "58000.00", "2900.00"),
                box("R2", "10", "5000.00", "250.00"),
            ],
        },
        {
            "exceptions": 0,
            "blocked": False,
            "assertions": [{"path": ["rows"], "length": 2}],
        },
        "Dubai allocations sum to 58000 and 2900. The separate declared input box is 5000 and 250. Only these two declared boxes are assessed, with no credit-eligibility or filing conclusion.",
        required_boxes=["1:DXB", "10"],
    )

    def pay(
        identifier,
        employee,
        amount,
        month="2026-06",
        payment="2026-06-28",
        due="2026-06-28",
    ):
        return {
            "id": identifier,
            "registration": "SYN-EST-ALNOOR",
            "subject": employee,
            "period": month,
            "component": "SALARY",
            "currency": "AED",
            "amount": amount,
            "due_date": due,
            "payment_date": payment,
        }

    payroll = [
        pay("P1", "SYN-EMP-001", "18500.00"),
        pay("P2", "SYN-EMP-002", "14750.00"),
        pay("P3", "SYN-EMP-003", "8250.00"),
    ]
    channel = [dict(r, id="WPS-" + r["id"]) for r in payroll]
    paid = [dict(r, id="BANK-" + r["id"]) for r in payroll if r["id"] != "P2"] + [
        pay("BANK-P2-A", "SYN-EMP-002", "9000.00"),
        pay("BANK-P2-B", "SYN-EMP-002", "5750.00"),
    ]
    add(
        "payroll-settlement",
        "three fictional employees and split bank settlement",
        {"payroll": payroll, "channel": channel, "bank": paid},
        {
            "exceptions": 0,
            "blocked": False,
            "assertions": [{"path": ["rows"], "length": 3}],
        },
        "Declared payroll 18500+14750+8250=41500. Employee 002 bank splits 9000+5750=14750. Due dates are assessed synthetic input facts, not UAE legal defaults.",
    )
    arrears = [
        pay("JUNE", "SYN-EMP-001", "18500.00"),
        pay("APRIL", "SYN-EMP-001", "3500.00", "2026-04"),
    ]
    add(
        "payroll-settlement",
        "arrears retain their original earning month",
        {
            r: [dict(p, id=r + "-" + p["id"]) for p in arrears]
            for r in ["payroll", "channel", "bank"]
        },
        {"exceptions": 0, "assertions": [{"path": ["rows"], "length": 2}]},
        "June 18500 and April arrears 3500 are two distinct earning-month partitions, total cash 22000. They are not merged into a June-only liability.",
    )
    late = deepcopy(paid)
    late[1]["payment_date"] = "2026-06-30"
    add(
        "payroll-settlement",
        "late bank date remains separate from amount agreement",
        {"payroll": payroll, "channel": channel, "bank": late},
        {
            "exceptions": 1,
            "rows_match": [{"subject": "SYN-EMP-003", "state": "LATE_PAYMENT"}],
        },
        "Employee 003 is paid 8250 in full on June 30 against the explicitly supplied June 28 due date. The amount ties, but timing is late.",
    )

    def stock(identifier, sku, qty, cost, nrv, condition="good"):
        return {
            "id": identifier,
            "site": "SYN-JEBEL-ALI-WH",
            "sku": sku,
            "uom": "EA",
            "currency": "AED",
            "quantity": qty,
            "unit_cost": cost,
            "unit_nrv": nrv,
            "ownership": "owned",
            "condition": condition,
            "count_date": "2026-06-30",
        }

    register = [
        stock("I1", "SYN-VALVE", "120", "85.00", "92.00"),
        stock("I2", "SYN-SEAL", "30", "380.00", "320.00"),
    ]
    counted = [
        stock("C1", "SYN-VALVE", "118", "85.00", "92.00"),
        stock("C2", "SYN-SEAL", "30", "380.00", "320.00", "damaged"),
    ]
    add(
        "stock-audit",
        "quantity shortage and damaged stock remain separate",
        {"books": register, "count": counted},
        {
            "exceptions": 2,
            "assertions": [
                {"path": ["coverage", "book_value"], "decimal_equals": "21600"},
                {
                    "path": ["coverage", "count_supported_value"],
                    "decimal_equals": "21430",
                },
            ],
            "rows_match": [
                {"sku": "SYN-VALVE", "state": "VARIANCE", "quantity_difference": "-2"},
                {
                    "sku": "SYN-SEAL",
                    "state": "CONDITION_EXCEPTION",
                    "potential_nrv_writedown": "1800.00",
                },
            ],
        },
        "Book value 120*85+30*380=21600. Count-supported value 118*85+30*380=21430. Seal NRV indicator (380-320)*30=1800. Declared counts do not establish physical attendance.",
    )
    add(
        "stock-audit",
        "full quantity coverage does not eliminate an NRV indicator",
        {"books": register, "count": [dict(r, id="C-" + r["id"]) for r in register]},
        {
            "exceptions": 1,
            "assertions": [{"path": ["coverage", "percent"], "decimal_equals": "100"}],
            "rows_match": [
                {
                    "sku": "SYN-SEAL",
                    "state": "NRV_WRITEDOWN",
                    "potential_nrv_writedown": "1800.00",
                }
            ],
        },
        "All 150 declared units agree by SKU. Quantity coverage is 100%; the separate 1800 NRV indicator remains.",
    )

    def evidence(identifier, subject, requirement, state="supported", expires="2026-12-31"):
        return {
            "id": identifier,
            "subject": subject,
            "requirement": requirement,
            "state": state,
            "evidence_reference": "SYNTHETIC-LOCAL-ASSESSMENT-" + identifier,
            "expires_on": expires,
            "rationale": "SYNTHETIC authored evidence assessment; no live registry or bank authentication",
        }

    vendors = [
        evidence("V1-L", "SYN-VENDOR-001", "licence"),
        evidence("V1-B", "SYN-VENDOR-001", "bank-change-approval", "not-applicable"),
        evidence("V2-L", "SYN-VENDOR-002", "licence"),
    ]
    add(
        "vendor-diligence",
        "new vendor bank details require their own approval",
        {"checks": vendors},
        {
            "exceptions": 1,
            "blocked": True,
            "rows_match": [
                {
                    "subject": "SYN-VENDOR-002",
                    "requirement": "bank-change-approval",
                    "state": "MISSING",
                }
            ],
        },
        "Two vendors times two scoped checks gives four decisions. Vendor 002 has no bank-change approval. A supported licence does not clear it.",
        subjects=["SYN-VENDOR-001", "SYN-VENDOR-002"],
        required_checks=["licence", "bank-change-approval"],
    )
    add(
        "nonprofit-diligence",
        "separate fictional foundation with expired registry evidence",
        {
            "checks": [
                evidence(
                    "NPO-R",
                    "SYN-GULF-RELIEF-FOUNDATION",
                    "registry",
                    expires="2026-05-31",
                ),
                evidence("NPO-G", "SYN-GULF-RELIEF-FOUNDATION", "grant-controls"),
            ]
        },
        {"exceptions": 1, "blocked": True, "state": "EXPIRED"},
        "The foundation is a separate fictional entity, not the trading company. May 31 registry evidence is expired at June 30; grant controls cannot replace it.",
        subjects=["SYN-GULF-RELIEF-FOUNDATION"],
        required_checks=["registry", "grant-controls"],
    )
    add(
        "controls",
        "documented incompatible payment access stays an exception",
        {
            "checks": [
                evidence("SOD", "SYN-ERP-PAYABLES", "segregation-of-duties", "exception"),
                evidence("LOG", "SYN-ERP-PAYABLES", "access-log"),
            ]
        },
        {"exceptions": 1, "blocked": False, "state": "EXCEPTION"},
        "A fictional preparer/approver access conflict is an assessed exception, not a successful controls-effectiveness conclusion. Review disposition remains a separate workflow.",
        subjects=["SYN-ERP-PAYABLES"],
        required_checks=["segregation-of-duties", "access-log"],
    )
    add(
        "tax-close",
        "VAT tie does not complete unassessed corporate-tax group scope",
        {
            "checks": [
                evidence("TC-VAT", "SYN-ALNOOR-ENTITY", "vat201-ledger-tie"),
                evidence(
                    "TC-FOR",
                    "SYN-ALNOOR-ENTITY",
                    "foreign-withholding-scope",
                    "not-applicable",
                ),
            ]
        },
        {
            "exceptions": 1,
            "blocked": True,
            "rows_match": [
                {
                    "subject": "SYN-ALNOOR-ENTITY",
                    "requirement": "ct-tax-group-scope",
                    "state": "MISSING",
                }
            ],
        },
        "Three required decisions; corporate-tax group scope is absent. Domestic UAE has no automatic Indian PF/PT/TDS rule. Explicit foreign-scope non-applicability is a synthetic assessed input.",
        subjects=["SYN-ALNOOR-ENTITY"],
        required_checks=[
            "vat201-ledger-tie",
            "ct-tax-group-scope",
            "foreign-withholding-scope",
        ],
    )
    return cases
