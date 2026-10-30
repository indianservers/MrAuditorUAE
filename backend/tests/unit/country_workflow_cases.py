"""Curated synthetic scenarios with independently specified expected behavior.

These exercise operational evidence workflows, not legal rate qualification.
"""

from copy import deepcopy


def transaction(**changes):
    return {
        "id": "1",
        "account": "BANK-1",
        "reference": "PAY-1",
        "date": "2026-06-01",
        "currency": "AED",
        "amount": "100",
        "counterparty": "Customer",
        **changes,
    }


def document(**changes):
    return {
        "id": "1",
        "registration": "REG-1",
        "counterparty": "SUP-1",
        "reference": "INV-1",
        "period": "2026-06",
        "date": "2026-06-01",
        "currency": "AED",
        "document_type": "invoice",
        "net": "100",
        "tax": "5",
        "component": "VAT",
        "status": "active",
        **changes,
    }


def obligation(**changes):
    return {
        "id": "1",
        "registration": "EMPLOYER-1",
        "subject": "EMP-1",
        "period": "2026-05",
        "component": "SALARY",
        "currency": "AED",
        "amount": "100",
        "due_date": "2026-06-05",
        "payment_date": "2026-06-01",
        **changes,
    }


def stock(**changes):
    return {
        "id": "1",
        "site": "WH-1",
        "sku": "SKU-1",
        "uom": "EA",
        "currency": "AED",
        "quantity": "10",
        "unit_cost": "10",
        "unit_nrv": "12",
        "ownership": "owned",
        "condition": "good",
        "count_date": "2026-06-30",
        **changes,
    }


def check(**changes):
    return {
        "id": "1",
        "subject": "ENTITY-1",
        "requirement": "licence",
        "state": "supported",
        "evidence_reference": "retained-document-1",
        "expires_on": "2026-12-31",
        "rationale": "Reviewed source scope",
        **changes,
    }


CASES = []


def add(workflow, title, sources, expected, country="AE", **parameters):
    CASES.append(
        {
            "id": f"RW-{len(CASES) + 1:03}",
            "title": title,
            "workflow": workflow,
            "country": country,
            "sources": deepcopy(sources),
            "expected": expected,
            "parameters": parameters,
        }
    )


b = {"books": [transaction()], "statement": [transaction(id="S1")]}
defaults = dict(
    account="BANK-1",
    book_opening="0",
    book_closing="100",
    statement_opening="0",
    statement_closing="100",
)


def bank_case(title, sources, expected, **parameters):
    add("bank-brs", title, sources, expected, **{**defaults, **parameters})


bank_case("UAE exact bank receipt ties to cashbook", b, {"exceptions": 0, "blocked": False})
for title, left, right, bc, sc in [
    (
        "Unpresented cheque remains open",
        [transaction(amount="-100", reference="CHQ-1")],
        [transaction(id="S1", amount="20", reference="OTHER")],
        "-100",
        "20",
    ),
    (
        "Deposit awaits bank credit",
        [transaction(amount="100")],
        [transaction(id="S1", amount="20", reference="OTHER")],
        "100",
        "20",
    ),
    (
        "Bank fee not recorded in cashbook",
        [transaction()],
        [transaction(id="S1"), transaction(id="S2", amount="-5", reference="FEE")],
        "100",
        "95",
    ),
    (
        "Bank interest not recorded in cashbook",
        [transaction()],
        [transaction(id="S1"), transaction(id="S2", amount="5", reference="INT")],
        "100",
        "105",
    ),
]:
    bank_case(
        title,
        {"books": left, "statement": right},
        {"exceptions": 2 if len(right) == 1 else 1, "blocked": False},
        book_closing=bc,
        statement_closing=sc,
    )
bank_case(
    "Unexplained opening balance difference blocks approval",
    b,
    {"blocked": True},
    book_opening="1",
    book_closing="101",
)
bank_case(
    "Incomplete cashbook population fails closing control", b, {"blocked": True}, book_closing="105"
)
bank_case(
    "Incomplete statement population fails closing control",
    b,
    {"blocked": True},
    statement_closing="105",
)
bank_case(
    "Foreign currency statement cannot clear AED cashbook",
    {"books": b["books"], "statement": [transaction(currency="USD")]},
    {"error": "single selected account"},
)
bank_case(
    "Wrong bank account cannot clear selected account",
    {"books": b["books"], "statement": [transaction(account="BANK-2")]},
    {"error": "single selected account"},
)
bank_case(
    "Identical receipt amounts stay ambiguous",
    {
        "books": b["books"],
        "statement": [transaction(id="S1", reference=""), transaction(id="S2", reference="")],
    },
    {"exceptions": 3, "blocked": False},
    statement_closing="200",
)
bank_case(
    "Old outstanding cheque is visibly stale",
    {
        "books": [transaction(date="2026-01-01", amount="-100")],
        "statement": [transaction(id="S1", amount="20")],
    },
    {"stale": True},
    book_closing="-100",
    statement_closing="20",
)
bank_case(
    "Split settlement ties by bounded reference group",
    {
        "books": [transaction(amount="40"), transaction(id="2", amount="60")],
        "statement": [transaction(id="S1")],
    },
    {"exceptions": 0, "blocked": False},
)
bank_case(
    "Receipt reversal retained as an independent item",
    {
        "books": [transaction(), transaction(id="2", amount="-100", reference="REV")],
        "statement": [transaction(id="S1"), transaction(id="S2", amount="-100", reference="REV")],
    },
    {"exceptions": 0, "blocked": False},
    book_closing="0",
    statement_closing="0",
)
bank_case(
    "Matching tolerance never hides BRS residual",
    {"books": b["books"], "statement": [transaction(id="S1", amount="99.99")]},
    {"blocked": True},
    statement_closing="99.99",
    tolerance="0.01",
)
bank_case(
    "Future-dated bank settlement rejected",
    {"books": b["books"], "statement": [transaction(id="S1", date="2026-07-01")]},
    {"error": "after the reconciliation date"},
)

for workflow, country, component in [("uae-vat", "AE", "VAT"), ("india-gst", "IN", "CGST")]:
    d = document(component=component, currency="INR" if country == "IN" else "AED")

    def tax_case(title, left, right, expected, **params):
        add(
            workflow,
            f"{country} {title}",
            {"books": left, "return": right},
            expected,
            country,
            currency="INR" if country == "IN" else "AED",
            **params,
        )

    tax_case("invoice independently agrees", [d], [{**d, "id": "R1"}], {"state": "MATCHED"})
    for kind, title, value in [
        ("credit-note", "credit note retained separately", "-5"),
        ("debit-note", "debit note retained separately", "5"),
    ]:
        item = {
            **d,
            "document_type": kind,
            "net": "-100" if kind == "credit-note" else "100",
            "tax": value,
        }
        tax_case(title, [item], [{**item, "id": "R1"}], {"state": "MATCHED"})
    tax_case(
        "invoice absent from return",
        [d],
        [{**d, "id": "R1", "reference": "OTHER"}],
        {"state": "BOOKS_ONLY"},
    )
    tax_case(
        "invoice absent from books",
        [{**d, "reference": "ZZZ"}],
        [{**d, "id": "R1"}],
        {"state": "RETURN_ONLY"},
    )
    tax_case(
        "tax amount differs",
        [d],
        [{**d, "id": "R1", "tax": "4"}],
        {"state": "VARIANCE", "tax_difference": "1"},
    )
    tax_case(
        "taxable base differs despite equal tax",
        [d],
        [{**d, "id": "R1", "net": "90"}],
        {"state": "VARIANCE"},
    )
    tax_case(
        "late filing creates period difference",
        [d],
        [{**d, "id": "R1", "period": "2026-05"}],
        {"state": "PERIOD_DIFFERENCE"},
    )
    tax_case(
        "rejected portal document stays visible",
        [d],
        [{**d, "id": "R1", "status": "rejected"}],
        {"state": "REJECTED_ON_RETURN"},
    )
    tax_case(
        "pending portal document cannot be clean",
        [d],
        [{**d, "id": "R1", "status": "pending"}],
        {"state": "SOURCE_STATUS_PENDING"},
    )
    tax_case(
        "amendment duplicates cannot be summed",
        [d],
        [{**d, "id": "R1"}, {**d, "id": "R2", "reference": "INV1"}],
        {"error": "Duplicate domain key"},
    )
    tax_case(
        "registration boundaries prevent false matching",
        [d],
        [{**d, "id": "R1", "registration": "REG-2"}],
        {"state": "BOOKS_ONLY"},
    )

for workflow, country, roles, component in [
    ("payroll-settlement", "AE", ["payroll", "channel", "bank"], "SALARY"),
    ("statutory-dues", "IN", ["expected", "return", "payment"], "PF:EMPLOYEE"),
    ("india-withholding", "IN", ["books", "return", "payment"], "TDS:DEDUCTOR"),
]:
    o = obligation(component=component)
    src = {r: [{**o, "id": r + "1"}] for r in roles}

    def dues_case(title, edits, expected):
        add(workflow, f"{country} {title}", {**src, **edits}, expected, country)

    dues_case("three-way settlement agrees", {}, {"state": "MATCHED"})
    dues_case(
        "underpayment remains quantified",
        {roles[-1]: [{**o, "amount": "90"}]},
        {"state": "VARIANCE"},
    )
    dues_case(
        "missing payment partition remains missing",
        {roles[-1]: [{**o, "subject": "ZZZ"}]},
        {"state": "MISSING_SOURCE_PARTITION"},
    )
    dues_case(
        "late bank payment stays an exception",
        {roles[-1]: [{**o, "payment_date": "2026-06-06"}]},
        {"state": "LATE_PAYMENT"},
    )
    dues_case(
        "missing due date cannot prove timely settlement",
        {roles[-1]: [{**o, "due_date": None}]},
        {"state": "TIMING_NOT_VERIFIED"},
    )
    dues_case(
        "split payment reconciles without duplicate allocation",
        {roles[-1]: [{**o, "id": "p1", "amount": "40"}, {**o, "id": "p2", "amount": "60"}]},
        {"state": "MATCHED"},
    )
    dues_case(
        "arrears retain their wage month",
        {r: [{**o, "id": r + "1", "period": "2026-04"}] for r in roles},
        {"state": "MATCHED"},
    )
    dues_case(
        "different employee cannot clear payroll",
        {roles[-1]: [{**o, "subject": "OTHER"}]},
        {"state": "MISSING_SOURCE_PARTITION"},
    )
    dues_case(
        "different employer registration stays separate",
        {roles[-1]: [{**o, "registration": "OTHER"}]},
        {"state": "MISSING_SOURCE_PARTITION"},
    )
    dues_case(
        "employer and employee components cannot net",
        {roles[-1]: [{**o, "component": component + ":OTHER"}]},
        {"state": "MISSING_SOURCE_PARTITION"},
    )
    dues_case(
        "negative correction requires explicit allocation adapter",
        {roles[-1]: [{**o, "amount": "-1"}]},
        {"error": "negative settlements"},
    )
    dues_case(
        "future payment cannot settle current dues",
        {roles[-1]: [{**o, "payment_date": "2026-07-01"}]},
        {"error": "Future payment"},
    )

s = stock()
stock_variants = [
    ("Item count and book quantity agree", {}, {}, "MATCHED"),
    ("Book item has no matching count", {}, {"sku": "ZZZ"}, "BOOKS_ONLY"),
    ("Physical count item absent from book register", {"sku": "ZZZ"}, {}, "COUNT_ONLY"),
    ("Count shortage is quantified", {}, {"quantity": "8"}, "VARIANCE"),
    ("NRV impairment remains visible", {"unit_nrv": "8"}, {}, "NRV_WRITEDOWN"),
    (
        "Inventory ownership not confirmed",
        {},
        {"ownership": "unconfirmed"},
        "OWNERSHIP_UNCONFIRMED",
    ),
    (
        "Consignment stock is not treated as owned",
        {},
        {"ownership": "third-party"},
        "OWNERSHIP_UNCONFIRMED",
    ),
    (
        "Expired inventory condition requires action",
        {},
        {"condition": "expired"},
        "CONDITION_EXCEPTION",
    ),
    (
        "Count before year end requires movement bridge",
        {},
        {"count_date": "2026-06-29"},
        "COUNT_DATE_BRIDGE_REQUIRED",
    ),
    ("Negative stock requires investigation", {"quantity": "-1"}, {}, "NEGATIVE_QUANTITY"),
    ("Missing NRV is not a clean valuation", {"unit_nrv": None}, {}, "VALUATION_INPUT_MISSING"),
    ("Different units of measure cannot be added", {}, {"uom": "KG"}, "BOOKS_ONLY"),
    ("Different warehouses cannot clear each other", {}, {"site": "WH-2"}, "BOOKS_ONLY"),
]
for title, bchanges, cchanges, state in stock_variants:
    add(
        "stock-audit",
        title,
        {"books": [{**s, **bchanges}], "count": [{**s, "id": "C1", **cchanges}]},
        {"state": state},
    )
add(
    "stock-audit",
    "Future stock count requires a separate roll-back procedure",
    {"books": [s], "count": [stock(count_date="2026-07-01")]},
    {"error": "Future inventory"},
)

for workflow, requirement, country in [
    ("controls", "access-review", "AE"),
    ("vendor-diligence", "trade-licence", "AE"),
    ("nonprofit-diligence", "fundraising-permit", "AE"),
    ("tax-close", "tax-period-assessment", "IN"),
]:
    c = check(requirement=requirement)

    def check_case(title, edits, expected, **parameters):
        add(
            workflow,
            f"{requirement}: {title}",
            {"checks": [{**c, **edits}]},
            expected,
            country,
            required_checks=[requirement],
            subjects=["ENTITY-1"],
            **parameters,
        )

    check_case(
        "retained evidence supports scoped check", {}, {"state": "SUPPORTED", "blocked": False}
    )
    check_case(
        "expired evidence cannot establish current compliance",
        {"expires_on": "2026-06-29"},
        {"state": "EXPIRED", "blocked": True},
    )
    check_case(
        "expiry on review date remains current",
        {"expires_on": "2026-06-30"},
        {"state": "SUPPORTED"},
    )
    check_case(
        "declared support without reference stays missing",
        {"evidence_reference": ""},
        {"state": "EVIDENCE_MISSING", "blocked": True},
    )
    check_case(
        "documented exception requires disposition",
        {"state": "exception"},
        {"state": "EXCEPTION", "exceptions": 1},
    )
    check_case(
        "unknown status is not clean", {"state": "missing"}, {"state": "MISSING", "blocked": True}
    )
    check_case(
        "justified non-applicability retained",
        {"state": "not-applicable"},
        {"state": "NOT-APPLICABLE"},
    )
    check_case(
        "unexplained non-applicability blocked",
        {"state": "not-applicable", "rationale": ""},
        {"state": "RATIONALE_MISSING", "blocked": True},
    )
    check_case(
        "missing scoped check visible despite other evidence",
        {"requirement": "OTHER"},
        {"state": "MISSING", "blocked": True},
    )
    add(
        workflow,
        f"{requirement}: whole missing entity is visible",
        {"checks": [c]},
        {"state": "MISSING", "blocked": True},
        country,
        required_checks=[requirement],
        subjects=["ENTITY-0", "ENTITY-1"],
    )


def return_box(**changes):
    return {
        "id": "1",
        "registration": "TRN-1",
        "period_start": "2026-04-01",
        "period_end": "2026-06-30",
        "box": "1:DXB",
        "currency": "AED",
        "taxable_amount": "100",
        "tax": "5",
        "adjustment": "0",
        **changes,
    }


v = return_box()


def vat_case(title, books, filed, expected, boxes=None):
    add(
        "uae-vat-return",
        title,
        {"books": books, "return": filed},
        expected,
        required_boxes=boxes or ["1:DXB"],
    )


vat_case(
    "UAE VAT201 declared box agrees to register", [v], [{**v, "id": "R1"}], {"state": "MATCHED"}
)
vat_case(
    "UAE VAT201 multiple book rows aggregate without netting tax fields",
    [
        return_box(id="B1", taxable_amount="40", tax="2"),
        return_box(id="B2", taxable_amount="60", tax="3"),
    ],
    [{**v, "id": "R1"}],
    {"state": "MATCHED"},
)
vat_case(
    "UAE VAT201 tax variance is distinct from base variance",
    [v],
    [return_box(id="R1", tax="4")],
    {"state": "VARIANCE"},
)
vat_case(
    "UAE VAT201 taxable-base variance survives equal tax",
    [v],
    [return_box(id="R1", taxable_amount="90")],
    {"state": "VARIANCE"},
)
vat_case(
    "UAE VAT201 adjustment is independently compared",
    [v],
    [return_box(id="R1", adjustment="1")],
    {"state": "VARIANCE"},
)
vat_case(
    "UAE VAT201 book box absent from filed return",
    [v],
    [return_box(id="R1", box="9")],
    {"state": "BOOKS_ONLY"},
)
vat_case(
    "UAE VAT201 filed box absent from book mapping",
    [return_box(box="9")],
    [{**v, "id": "R1"}],
    {"state": "RETURN_ONLY"},
)
vat_case(
    "UAE VAT201 required box absent from both sources is missing",
    [v],
    [{**v, "id": "R1"}],
    {"exceptions": 1, "blocked": True},
    boxes=["1:DXB", "9"],
)
vat_case(
    "UAE VAT201 duplicate amended return boxes cannot be added",
    [v],
    [{**v, "id": "R1"}, {**v, "id": "R2"}],
    {"error": "Duplicate domain key"},
)
vat_case(
    "UAE VAT201 different tax registrations stay separate",
    [v],
    [return_box(id="R1", registration="TRN-2")],
    {"state": "BOOKS_ONLY"},
)
vat_case(
    "UAE VAT201 different assigned tax periods stay separate",
    [v],
    [return_box(id="R1", period_start="2026-01-01", period_end="2026-03-31")],
    {"exceptions": 2},
)
vat_case(
    "UAE VAT201 future tax period cannot close early",
    [v],
    [return_box(id="R1", period_end="2026-07-31")],
    {"error": "beyond the reconciliation date"},
)

dues_parameters = dict(
    account="BANK-1",
    obligation_month_start="2026-05",
    obligation_month_end="2026-05",
    settlement_start="2026-06-01",
    bank_payment_sign="debit-negative",
)
dues_expected = [
    obligation(id="E1", payment_date=None),
    obligation(id="E2", subject="EMP-2", amount="80", payment_date=None),
]
dues_population = {
    "expected": dues_expected,
    "reported": [{**row, "id": "R" + row["id"][1:]} for row in dues_expected],
    "bank": [transaction(id="BANK", amount="-180")],
    "allocations": [
        {
            "id": f"A{index}",
            "expected_id": row["id"],
            "reported_id": "R" + row["id"][1:],
            "transaction_id": "BANK",
            "currency": "AED",
            "amount": row["amount"],
            "evidence_reference": "SYNTHETIC-PAYMENT-ADVICE",
            "rationale": "Reviewed fictional pooled salary payment allocation",
        }
        for index, row in enumerate(dues_expected, 1)
    ],
}
add(
    "obligation-bank-allocations",
    "UAE pooled bank debit settles two employee obligations",
    dues_population,
    {"exceptions": 0},
    **dues_parameters,
)
partial_dues = deepcopy(dues_population)
partial_dues["bank"][0]["amount"] = "-150"
partial_dues["allocations"][1]["amount"] = "50"
add(
    "obligation-bank-allocations",
    "UAE partially settled salary remains outstanding and overdue",
    partial_dues,
    {"exceptions": 2},
    **dues_parameters,
)
incoming_dues = deepcopy(dues_population)
incoming_dues["bank"].append(transaction(id="REFUND", amount="20"))
add(
    "obligation-bank-allocations",
    "UAE salary settlement never nets an unallocated bank credit",
    incoming_dues,
    {"exceptions": 1},
    **dues_parameters,
)
add(
    "obligation-bank-allocations",
    "UAE missing payroll month remains missing rather than zero",
    dues_population,
    {"exceptions": 1},
    **{**dues_parameters, "obligation_month_end": "2026-06"},
)
india_dues = deepcopy(dues_population)
for role, records in india_dues.items():
    for row in records:
        row["currency"] = "INR"
        if role in {"expected", "reported"}:
            row["component"] = "PF:EMPLOYEE"
add(
    "obligation-bank-allocations",
    "India pooled bank debit explicitly allocates employee PF dues",
    india_dues,
    {"exceptions": 0},
    country="IN",
    currency="INR",
    **dues_parameters,
)
overallocated_dues = deepcopy(india_dues)
overallocated_dues["allocations"][1]["amount"] = "81"
add(
    "obligation-bank-allocations",
    "India obligation or challan allocation cannot reuse excess cash",
    overallocated_dues,
    {"error": "overallocated"},
    country="IN",
    currency="INR",
    **dues_parameters,
)

for bank_country, bank_currency in [("AE", "AED"), ("IN", "INR")]:
    bank_assertion = {
        "id": "register-1",
        "account": "SYN-BANK",
        "bank_country": bank_country,
        "account_scheme": "IBAN" if bank_country == "AE" else "LOCAL",
        "account_number": "AE070331234567890123456" if bank_country == "AE" else "000123456789",
        "routing_code": "033" if bank_country == "AE" else "SYNB0ABC123",
        "currency": bank_currency,
        "owner_country": bank_country,
        "owner_name": "SYNTHETIC Entity LLC",
        "owner_identifier_scheme": "SYNTHETIC-REGISTRY",
        "owner_identifier": "00123",
        "valid_from": "2026-01-01",
        "valid_through": "2026-12-31",
        "assertion_status": "confirmed",
        "evidence_reference": "SYNTHETIC register",
        "assessment": "Independently specified synthetic account ownership evidence",
    }
    account_assertions = {
        role: [{**bank_assertion, "id": role + "-1", "evidence_reference": "SYNTHETIC " + role}]
        for role in ("register", "ledger", "bank")
    }
    if bank_country == "IN":
        account_assertions["bank"][0]["account_number"] = "123456789"
    add(
        "bank-account-evidence",
        "UAE register/ledger/bank owner evidence agrees without bank authentication"
        if bank_country == "AE"
        else "India leading-zero account mismatch cannot be approved as ownership evidence",
        account_assertions,
        {"exceptions": 0 if bank_country == "AE" else 1, "blocked": bank_country == "IN"},
        country=bank_country,
        account="SYN-BANK",
        currency=bank_currency,
        bank_owner_name="SYNTHETIC Entity LLC",
        bank_owner_identifier_scheme="SYNTHETIC-REGISTRY",
        bank_owner_identifier="00123",
    )

series_row = {
    "id": "SYN-SERIES-1",
    "registration": "27ABCDE5678G1Z8",
    "period": "2026-06",
    "doc_num": 1,
    "serial_from": "SYN/0001",
    "serial_to": "SYN/0010",
    "issued": 10,
    "cancelled": 2,
    "net_issued": 8,
}
series_sources = {role: [{**series_row, "id": "SYN-" + role}] for role in ("books", "reported")}
add(
    "india-document-series",
    "India document-series issued and cancelled counts agree with independent reported ranges",
    series_sources,
    {"exceptions": 0, "blocked": False},
    country="IN",
    currency="INR",
)
series_variance = deepcopy(series_sources)
series_variance["reported"][0].update(cancelled=1, net_issued=9)
add(
    "india-document-series",
    "India cancelled document count discrepancy survives a large money tolerance",
    series_variance,
    {"exceptions": 1, "blocked": False},
    country="IN",
    currency="INR",
    tolerance="1000",
)

tax_dues = deepcopy(india_dues)
for role in ("expected", "reported"):
    for index, tax_obligation in enumerate(tax_dues[role], 1):
        tax_obligation.update(
            period="2026-05",
            component="TDS",
            due_date="2026-06-30",
            withholding_scope={
                "legal_role": "deductor",
                "tax_kind": "TDS",
                "rule_reference": "SYN-ASSESSED-TDS-RULE",
                "tax_year_start": "2026-04-01",
                "tax_year_end": "2027-03-31",
                "transaction_reference": f"SYN-TAX-TX-{index}",
                "transaction_date": "2026-05-15",
            },
        )
tax_dues["bank"][0]["amount"] = "-150"
tax_dues["bank"].append(
    {**tax_dues["bank"][0], "id": "BANK2", "amount": "-30", "date": "2026-06-02"}
)
tax_dues["allocations"][1]["amount"] = "50"
tax_dues["allocations"].append(
    {**tax_dues["allocations"][1], "id": "A3", "transaction_id": "BANK2", "amount": "30"}
)
add(
    "obligation-bank-allocations",
    "India split and pooled withholding cash settlements retain each assessed transaction",
    tax_dues,
    {"exceptions": 0},
    country="IN",
    currency="INR",
    **{**dues_parameters, "obligation_month_end": "2026-05"},
)
wrong_tax_scope = deepcopy(tax_dues)
wrong_tax_scope["reported"][0]["withholding_scope"]["rule_reference"] = "SYN-DIFFERENT-TAX-SECTION"
add(
    "obligation-bank-allocations",
    "India withholding cash allocation cannot cross section scope despite matching amounts",
    wrong_tax_scope,
    {"error": "withholding scopes must also agree"},
    country="IN",
    currency="INR",
    **{**dues_parameters, "obligation_month_end": "2026-05"},
)

assert len(CASES) == 154
