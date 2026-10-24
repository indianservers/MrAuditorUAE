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
    d = document(component=component)

    def tax_case(title, left, right, expected, **params):
        add(
            workflow,
            f"{country} {title}",
            {"books": left, "return": right},
            expected,
            country,
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

assert len(CASES) == 142
