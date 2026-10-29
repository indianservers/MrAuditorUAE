"""Explicit published-field evidence inventory, not a filing or calculation schema.

Stable semantic keys distinguish main questions, schedule columns and fixed cells.
Repeated columns require complete-population workpapers, not one example party.
"""

from app.modules.jurisdictions.packages import fingerprint
from app.modules.regulatory.tax_forms import FORM_26_PUBLISHED, FORM_26_RULE

PREFIX = "india-form26-index:"
SOURCE_SHA = "03613f520b76f5e1de8194f08cce461fb863b57cd35bd0ca923cdd6df993f5a2"


def manifest(identifier):
    if identifier not in {PREFIX + "A/2", PREFIX + "B/2"}:
        raise ValueError("Unknown published-field Form 26 evidence inventory")
    part = identifier[len(PREFIX)]
    fields = []

    def add(ref, label, page, *, repeat=False, mandatory=False, printed=None):
        fields.append(
            {
                "key": "form26.field." + ref,
                "title": label,
                "page": page,
                "semantic_reference": ref,
                "printed_reference": printed,
                "population": "COMPLETE_REPEATED_POPULATION" if repeat else "FIXED_FIELD",
                "mandatory": mandatory,
                "entry_kind": "SOURCE_REVIEW_CONTROL"
                if ref.startswith("source_review.")
                else "POPULATION_CONTROL"
                if ref.endswith(".population")
                else "SOURCE_FIELD",
            }
        )

    def columns(ref, labels, page, printed=None, mandatory=False, repeat=True):
        add(
            ref + ".population",
            ref + " — population completeness, nil/applicability and source reconciliation",
            page,
            mandatory=mandatory,
        )
        for number, label in enumerate(labels.split("|"), 1):
            add(
                ref + f".c{number}",
                ref + " — " + label,
                page,
                repeat=repeat,
                mandatory=mandatory,
                printed=printed[number - 1] if printed else None,
            )

    def cells(ref, rows, cols, page):
        for row, label in rows:
            for column, column_label in cols:
                add(f"{ref}.{row}.{column}", f"{ref} {label} — {column_label}", page)

    signature = "Place|Date|Accountant signature assessment|Accountant name|Membership registration number|Accountant PAN|UDIN if any|Proprietorship or firm name|Firm registration number"
    if part == "A":
        columns(
            "A.1",
            "Assessee name|Statutory auditor identity|Act governing statutory audit",
            1,
            mandatory=True,
            repeat=False,
        )
        for key, title in [
            ("report_date", "Statutory audit report date"),
            ("report", "Attached statutory audit report"),
            ("pnl", "Audited profit and loss or income and expenditure account with notes"),
            ("period_start", "Audited account period beginning"),
            ("period_end", "Audited account period ending"),
            ("balance_date", "Balance sheet date"),
            ("balance", "Audited balance sheet with notes"),
            ("documents", "Documents required by governing Act"),
        ]:
            add("A.2." + key, title, 1, mandatory=True)
        add(
            "A.3.exists",
            "Statutory audit qualifications affecting income/loss/book profit",
            1,
            mandatory=True,
        )
        columns(
            "A.3.impact",
            "Serial number|Nature of qualification|Increase profit or decrease loss|Decrease profit or increase loss|Net impact not already in Part D|Remarks",
            1,
        )
        add("A.4", "Part D annexure assessment", 1, mandatory=True)
        add(
            "A.5.opinion",
            "Part D true/correct opinion and qualifications — professional assessment only",
            2,
            mandatory=True,
        )
    else:
        for key, title in [
            ("balance_date", "Examined balance sheet date"),
            ("period_start", "Account period beginning"),
            ("period_end", "Account period ending"),
            ("accounts", "Attached balance sheet and profit/loss or income/expenditure accounts"),
            ("head_office", "Head office books location"),
            ("branches", "Total number of branches"),
            ("agreement", "Accounts and notes agreement with books"),
            ("comments", "Observations/comments/discrepancies/inconsistencies"),
            ("qualifications", "Qualifications affecting income/loss/book profit"),
            ("information", "Information and explanations obtained"),
            ("proper_books", "Proper books at head office and branches"),
            ("balance_opinion", "True/fair state of affairs opinion"),
            ("pnl_opinion", "True/fair profit/loss or surplus/deficit opinion"),
        ]:
            add("B.report." + key, title, 3, mandatory=True)
        columns(
            "B.3.impact",
            "Serial number|Nature of qualification|Increase profit or decrease loss|Decrease profit or increase loss|Net impact not already in Part D|Remarks",
            3,
        )
        add("B.4", "Part D annexure assessment", 4, mandatory=True)
        add(
            "B.5.opinion",
            "Part D true/correct opinion and qualifications — professional assessment only",
            4,
            mandatory=True,
        )
    columns(
        part + ".observations",
        "Clause 9–53|Observation type|Qualification/observation or remarks",
        2 if part == "A" else 4,
    )
    for n, label in enumerate(signature.split("|"), 1):
        add(part + f".signature.{n}", label, 2 if part == "A" else 4, mandatory=True)
    for n, label in enumerate(
        "Full name|Country/region|Flat/door/building|Road/street/block/sector|PIN/ZIP|Area/locality|District|State|PAN|Person status|Residential status|Email|Contact country code|Contact number|Tax year".split(
            "|"
        ),
        1,
    ):
        add(f"C.identity.{n}", "Part C — " + label, 5, mandatory=True)
    add(
        "D.9.audit_basis",
        "Selected section 63 audit provision and assessed applicability",
        5,
        mandatory=True,
    )
    add("D.10", "Option under sections 199/200/201/202/203/204", 5)
    columns("D.11a", "Serial number|Partner/member name|PAN|Profit-sharing ratio", 5)
    for ref, label, page in [
        ("11b", "Change in partners/members or ratios", 5),
        ("12b", "Change in business/profession", 6),
        ("12c", "Cost audit carried out", 6),
        ("12c.report", "Attached cost audit report", 6),
        ("13", "All books maintained including computer books", 6),
        ("14b", "Accounting software", 6),
        ("14c.software", "Cloud/storage software", 6),
        ("14c.ip", "Storage IP address", 6),
        ("14c.country", "Storage country", 6),
        ("14d", "Rule 46(8) compliance", 6),
        ("14e", "India backup server address", 6),
        ("15a", "Mercantile or cash accounting method", 6),
        ("15b", "Accounting method changed", 6),
        ("16a.finished", "Finished goods inventory valuation method", 6),
        ("16a.raw", "Raw material inventory valuation method", 6),
        ("16b", "Section 277 valuation adjustment required", 7),
        ("17", "ICDS adjustment required", 7),
        ("18", "ICDS disclosure required", 7),
        ("19", "Presumptive income included in profit/loss", 7),
        (
            "20",
            "MAIN 20: section 92(2)(m) income not credited; schedule numbering conflict retained",
            8,
        ),
        ("21", "MAIN 21: other income not credited; schedule numbering conflict retained", 8),
        ("22", "Capital asset converted to stock", 8),
        ("23", "Property below stamp duty value", 8),
    ]:
        add("D." + ref, label, page)
    cells(
        "D.12d",
        [
            (str(i), label)
            for i, label in enumerate(
                [
                    "Total turnover",
                    "Gross profit/turnover",
                    "Net profit/turnover",
                    "Stock-in-trade/turnover",
                    "Material consumed/finished goods produced",
                ],
                1,
            )
        ],
        [("current", "Tax year"), ("previous", "Preceding tax year")],
        6,
    )
    columns("D.14a", "Serial number|Books location address|Books at this location", 6)
    for ref, label, page in [
        ("24", "Borrowing through negotiable instrument/hundi deemed income", 8),
        ("25", "Repayment including interest deemed income", 8),
        ("26", "Exempt-income expenditure inadmissible", 9),
        ("33a", "MSMED section 23 interest debited to profit/loss", 9),
        ("33b", "Current principal disallowance under 37(2)(g)", 9),
        ("33c", "Prior principal disallowance now allowable under 37(2)(g)", 9),
        ("37b", "Shareholding change causing section 119 loss restriction", 10),
        ("37c", "Speculation loss under 113(1)", 10),
        ("37d", "Deemed speculation business under 113(5)", 10),
        ("37e", "Specified business loss under 114", 10),
        ("42", "Disallowance under section 60", 10),
    ]:
        add("D." + ref + ".answer", label + " — applicability answer", page)
        add("D." + ref + ".amount", label + " — amount", page)
    for ref, page in [
        ("27a", 9),
        ("27b", 9),
        ("27c", 9),
        ("27d", 9),
        ("28", 9),
        ("29", 9),
        ("30", 9),
        ("31", 9),
        ("32a", 9),
        ("32b", 9),
        ("34", 9),
        ("35a", 10),
        ("35b", 10),
        ("36", 10),
        ("37a", 10),
        ("38", 10),
        ("39", 10),
        ("40", 10),
        ("41a", 10),
        ("41b", 10),
        ("41c", 10),
        ("43", 11),
        ("44", 11),
        ("45a", 11),
        ("45b", 11),
        ("45c", 11),
        ("45d", 11),
        ("46", 11),
        ("47", 11),
        ("48", 11),
        ("50a", 11),
        ("50b", 11),
        ("50c", 11),
        ("51a", 11),
        ("51b", 11),
        ("51c", 12),
        ("51d", 12),
        ("52", 12),
        ("53a", 12),
        ("53b", 12),
    ]:
        add(
            "D." + ref + ".answer",
            "Main item "
            + ref
            + " — explicit applicability answer and conditional schedule assessment",
            page,
        )
    add("D.49.TAN", "All TANs held by assessee", 11, repeat=True)
    for n, label in enumerate(signature.split("|"), 1):
        add(f"D.signature.{n}", "Part D — " + label, 12, mandatory=True)
    for ref, labels, page in [
        (
            "11b",
            "Serial number|Change date|Partner/member name|PAN|Change type|Old ratio percent|New ratio percent|Remarks",
            14,
        ),
        ("12a", "Serial number|Business/profession code|Description", 14),
        ("12b", "Serial number|Nature of change|Code|Description", 14),
        (
            "12cii",
            "Serial number|Cost audit disagreement particulars|Profit increase/loss decrease|Profit decrease/loss increase|Net effect|Remarks",
            14,
        ),
        (
            "15b",
            "Serial number|Method change particulars|Profit increase/loss decrease|Profit decrease/loss increase|Net effect|Remarks",
            15,
        ),
        ("19", "Serial number|Section|Presumptive profits and gains", 16),
        (
            "21",
            "Serial number|Asset type|Asset details|Transferor/payer name|Transferor/payer PAN|Consideration paid|Income under 92(2)(m)",
            17,
        ),
        (
            "22",
            "Serial number|Capital asset description|Acquisition date|Acquisition cost|Value on conversion to stock",
            17,
        ),
        (
            "23",
            "Serial number|Land/building type|Property address|Share in property|Consideration received/accrued|Stamp duty value|Section 53 or 78",
            17,
        ),
        ("27b", "Serial number|Fund nature ESI/PF/other|Disallowable deduction", 18),
        ("28", "Serial number|Law under which penalty levied|Section|Penalty amount", 20),
        (
            "29",
            "Serial number|Specified person name|PAN|Relationship|Transaction nature|Amount debited to profit/loss",
            20,
        ),
        (
            "30",
            "Serial number|Payment date|Payment nature|Disallowable amount|Payee name if available|Payee PAN if available|Payee Aadhaar if PAN unavailable",
            20,
        ),
        (
            "31",
            "Serial number|Payment date|Payment nature|Deemed income amount|Payee name if available|Payee PAN if available|Payee Aadhaar if PAN unavailable",
            20,
        ),
        ("32a", "Serial number|Section|Liability nature|Disallowable deduction", 20),
        ("32b", "Serial number|Section|Liability nature|Prior disallowance now allowable", 21),
        ("35a", "Serial number|Prior income nature|Amount|Prior tax year", 22),
        (
            "35b",
            "Serial number|Expenditure nature|Profit/loss debit|Prior tax year|Complete expenditure allowable yes/no|If not amount allowable",
            22,
        ),
        (
            "37a",
            "Serial number|Tax year|Loss/allowance nature|Returned amount subject to assessed/no appeal note|Disallowed under 200/202/203/204|Additional depreciation withdrawal adjustment under 202|Assessed amount with order|Remarks",
            25,
        ),
        ("38", "Chapter VIII section|Admissible deduction", 25),
        (
            "39",
            "Serial number|Tax year|Gross MAT/AMT credit subject to lower Form 66/67 and assessed/no appeal note|Earlier setoff|Brought-forward balance|Current utilization|Carried-forward balance|Remarks",
            26,
        ),
        (
            "40",
            "Serial number|Primary adjustment clause|Amount|Repatriation required under 170(2)|Repatriated within prescribed time|Imputed interest if not|Expected repatriation date",
            26,
        ),
        (
            "41a",
            "Interest/similar expenditure|EBITDA|Interest expenditure exceeding printed 30 percent of EBITDA",
            26,
        ),
        ("41b", "Tax year|Interest expenditure brought forward", 26),
        ("41c", "Tax year|Interest expenditure carried forward", 26),
        (
            "43",
            "Serial number|Remittance nature|Transaction count|Total remittances|Non-chargeable amount|Chargeable amount",
            26,
        ),
        (
            "44",
            "Serial number|Asset type|Asset details|Transferor/payer name|PAN|Relationship|Transaction nature|Consideration paid|Amount excluded under 92(2)(m)|Reason",
            28,
        ),
        (
            "45a",
            "Serial number|Loan/deposit/specified sum nature|Payer name|Payer PAN|Payer Aadhaar if available|Amount taken/accepted|Accepted through section 185(1) modes|Squared up in year|Maximum outstanding|Note 8 transaction code",
            28,
        ),
        (
            "45b",
            "Serial number|Payer name|Payer PAN|Payer Aadhaar if available|Transaction nature|Receipt amount|Receipt date|Note 8 transaction code",
            28,
        ),
        (
            "45c",
            "Serial number|Payee name|Payee PAN|Payee Aadhaar if available|Transaction nature|Payment amount|Payment date|Note 8 transaction code",
            28,
        ),
        (
            "45d",
            "Serial number|Repayment nature|Payee name|Payee PAN|Payee Aadhaar if available|Repayment amount INR|Maximum outstanding|Note 8 transaction code",
            28,
        ),
        (
            "46",
            "Reporting entity identification number|Form 98/165/166/167|Due date|Furnished as at audit date|Furnishing date|Reported transaction count|Unreported transaction count|Unreported transaction amount",
            29,
        ),
        (
            "47",
            "Serial number|Acquisition/transfer|Issuer name|Issuer PAN|Transaction date|Share count|Face value per share|Book value per share|Market value per share|Total cost/consideration|Acquisition income under 92(2)(m)|Transfer deemed consideration under 79|Transfer capital gains",
            29,
        ),
        ("48", "Serial number|Recipient name|Recipient PAN|Payment date|Amount paid", 29),
        (
            "50a",
            "TAN|Section|Payment/receipt nature|Total payment/receipt|Required withholding base out of D|Statutory rate base out of E|Tax on F|Lower rate base printed out of G|Tax on H|Undeposited tax printed out of F and H",
            30,
        ),
        (
            "50b",
            "TAN|Form type|Statement due date|Statement furnishing date|Reported transaction count latest correction|Unreported transaction count latest correction|Unreported transaction amount latest correction",
            30,
        ),
        ("50c", "TAN|Interest payable under 398(3)(a)|Interest paid out of B|Payment date", 30),
        (
            "51a",
            "Serial number|Violation nature|Expenditure nature|Payee name|Payee PAN|Amount|Disallowable amount printed 30 percent of F",
            31,
        ),
        (
            "51b",
            "Serial number|Expenditure nature|Prior tax year|Prior disallowed amount now allowable|Current allowable amount",
            31,
        ),
        (
            "51c",
            "Serial number|Violation nature|Expenditure nature|Payee name|Payee PAN|Amount|Disallowable amount printed 100 percent of F",
            31,
        ),
        (
            "51d",
            "Serial number|Expenditure nature|Prior tax year|Prior disallowed amount now allowable|Current allowable amount",
            32,
        ),
        ("52a", "Serial number|Indirect tax type|Registration/identification number", 32),
    ]:
        columns("schedule." + ref, labels, page)
    for ref, rows, page in [
        ("16b", ["277(1)(i)", "277(1)(ii)", "277(1)(iii)", "277(1)(iv)"], 15),
        (
            "17",
            [
                "ICDS I",
                "ICDS II excluding 16b",
                "ICDS III",
                "ICDS IV",
                "ICDS V",
                "ICDS VI",
                "ICDS VII",
                "ICDS VIII excluding 16b",
                "ICDS IX",
                "ICDS X",
                "Total",
            ],
            15,
        ),
    ]:
        cells(
            "schedule." + ref,
            [(str(i), r) for i, r in enumerate(rows, 1)],
            [
                ("increase", "Profit increase/loss decrease"),
                ("decrease", "Profit decrease/loss increase"),
                ("net", "Net effect"),
                ("remarks", "Remarks"),
            ],
            page,
        )
    cells(
        "schedule.18",
        [
            (str(i), r)
            for i, r in enumerate(
                [
                    "ICDS I",
                    "ICDS II",
                    "ICDS III",
                    "ICDS IV",
                    "ICDS V",
                    "ICDS VII",
                    "ICDS IX",
                    "ICDS X",
                ],
                1,
            )
        ],
        [("disclosure", "Disclosure")],
        16,
    )
    for ref, labels, page in [
        (
            "20",
            "2(40)(e)|2(40)(f)|26 excluding 16b|38|48 Schedule IX|49 Schedule X|92(2)(h)|92(2)(k)|278(1)|278(2)|277(3) with 2(49)(w)|Other income|Capital receipts",
            16,
        ),
        (
            "27a",
            "29(1)(a) employer fund|29(1)(b) with 124 pension|29(3) employer institution|32(a) bonus/commission|29(2) gratuity provision|31(1) doubtful debt|31(2) bad debt|32(b) asset borrowing interest|32(d) zero coupon discount|32(e) special reserve|32(h) marked-to-market loss|32(i) family planning|Contingent liability",
            18,
        ),
        (
            "27c",
            "Capital expenditure|Personal expenditure|Political advertisement|Club entrance/subscription|Club services|Offence/prohibition|Benefit/perquisite 34(3)(b)|Compounding offence|Notified proceeding settlement|Other such purpose|CSR|Total",
            19,
        ),
        ("27d", "35(a)|35(b)(iii)|35(c)|35(d)|35(e)|35(f)", 19),
        ("34b", "48 Schedule IX|49 Schedule X", 21),
        ("52b", "GST registered entities|GST unregistered entities|GST exempt goods/services", 32),
    ]:
        cells(
            "schedule." + ref,
            [(str(i), label) for i, label in enumerate(labels.split("|"), 1)],
            [("amount", "Amount")],
            page,
        )
    cells(
        "schedule.34a",
        [
            (str(i), r)
            for i, r in enumerate(
                [
                    "45(1)(a)(i)",
                    "45(1)(a)(ii)",
                    "45(1)(b)",
                    "45(2)",
                    "45(3)(a)(i)",
                    "45(3)(a)(ii)",
                    "45(3)(b)",
                    "45(3)(c)",
                    "47(1)(a)",
                    "47(1)(b)",
                    "46",
                    "44",
                    "51",
                    "52 table 1",
                    "52 table 2",
                    "52 table 3",
                    "52 table 4",
                    "Other relevant section",
                ],
                1,
            )
        ],
        [
            ("pnl", "P&L debit"),
            ("allowable", "Allowable deduction"),
            ("excess", "Excess deduction printed D minus C"),
        ],
        21,
    )
    for ref, page in [("51a", 31), ("51b", 31), ("51c", 31), ("51d", 32)]:
        add("schedule." + ref + ".total", ref + " total disallowable/allowable amount", page)
    base_rows = [
        ("3", "Opening WDV"),
        ("4", "Additions at least 180 days"),
        ("5", "Realizations out of 3 or 4"),
        ("6", "Full-rate base max(3+4-5,0)"),
        ("7", "Additions less than 180 days"),
        ("8", "Realizations out of 7"),
        ("9", "Half-rate base max(7-8,0)"),
        ("10", "Full-rate depreciation on 6"),
        ("11", "Half-rate depreciation on 9"),
    ]
    plant_rows = base_rows + [
        ("12", "Additional depreciation on 4"),
        ("13", "Additional depreciation on 7"),
        ("14", "Prior short-use additional depreciation"),
        ("15", "Total depreciation 10+11+12+13+14"),
        ("16", "Disallowed under 33(3)(b)"),
        ("17", "Net depreciation 15-16"),
        ("18", "Succession proportion out of 17"),
        ("19", "Transfer expenditure"),
        ("20", "Capital gain/loss 5+8-3-4-7-19 conditional negative"),
        ("21", "Closing WDV max(6+9-15,0)"),
    ]
    other_rows = base_rows + [
        ("12", "Total depreciation 10+11"),
        ("13", "Disallowed under 33(3)(b)"),
        ("14", "Net depreciation 12-13"),
        ("15", "Succession proportion out of 14"),
        ("16", "Transfer expenditure"),
        ("17", "Capital gain/loss 5+8-3-4-7-16 conditional negative"),
        ("18", "Closing WDV max(6+9-12,0)"),
    ]
    cells(
        "schedule.36.plant",
        plant_rows,
        [
            ("p15", "Plant 15 percent printed i"),
            ("p30", "Plant 30 percent printed ii"),
            ("p40", "Plant 40 percent printed iii"),
            ("p45", "Plant 45 percent printed iv"),
        ],
        23,
    )
    cells(
        "schedule.36.other",
        other_rows,
        [
            ("land", "Land Nil printed i"),
            ("building5", "Building 5 printed ii"),
            ("building10", "Building 10 printed iii"),
            ("building40", "Building 40 printed iv"),
            ("furniture", "Furniture 10 printed v"),
            ("intangible", "Intangible 25 printed vi"),
            ("ships", "Ships 20 printed viii"),
        ],
        24,
    )
    for ref, movements, extra in [
        ("53a", ["Opening stock", "Purchases", "Sales", "Closing stock", "Shortage/excess"], []),
        (
            "53bi",
            ["Opening stock", "Purchases", "Consumption", "Sales", "Closing stock"],
            ["Yield of finished products", "Yield percent"],
        ),
        (
            "53bii",
            [
                "Opening stock",
                "Purchases",
                "Manufactured",
                "Sales",
                "Closing stock",
                "Shortage/excess",
            ],
            [],
        ),
    ]:
        quantity_labels = ["Serial number", "Principal goods description", "Unit name"]
        for movement in movements:
            quantity_labels += [movement + " quantity", movement + " value"]
        quantity_labels += extra
        if ref == "53bi":
            quantity_labels += ["Shortage/excess quantity", "Shortage/excess value"]
        columns("schedule." + ref, "|".join(quantity_labels), 33)
    for ref, label, page in [
        (
            "category_conflict",
            "Page 1 category instruction conflict — assess Rule 47 and report headings",
            1,
        ),
        (
            "income_numbering_conflict",
            "Main 20/21 and schedule 20/21 source-caption conflict — preserve both references",
            17,
        ),
        (
            "column_identifiers",
            "Printed column identifiers differ from semantic cells on pages 24, 28 and 33",
            33,
        ),
        (
            "withholding_crossrefs",
            "Printed 50a H/J cross-references require professional/source assessment, not inferred arithmetic",
            30,
        ),
    ]:
        add("source_review." + ref, label, page, mandatory=True)
    add(
        "source_review.notes",
        "Notes 1–10: identity, qualification reasons, currency, rounding, codes and narrative assessment",
        13,
        mandatory=True,
    )
    # Continuation pages are explicit; a schedule heading page is not every cell's source.
    for field in fields:
        key = field["key"]
        if key.startswith("form26.field.schedule.36.plant.") and int(key.split(".")[-2]) >= 19:
            field["page"] = 24
        elif key.startswith("form26.field.schedule.36.other.") and int(key.split(".")[-2]) >= 13:
            field["page"] = 25
        elif key.startswith("form26.field.schedule.17.") and int(key.split(".")[-2]) >= 9:
            field["page"] = 16
        elif key.startswith("form26.field.schedule.20.") and int(key.split(".")[-2]) >= 10:
            field["page"] = 17
        elif key.startswith("form26.field.schedule.27c.") and int(key.split(".")[-2]) <= 3:
            field["page"] = 18
    for ref, label, page in [
        ("schedule.34a.18.section", "Other relevant deduction section", 21),
        ("schedule.20.12.description", "Other uncredited income description", 17),
        ("schedule.20.13.description", "Uncredited capital receipt description", 17),
    ]:
        add(ref, label, page, repeat=True)
    transaction_codes = dict(
        zip(
            "ABCDEFGHIJKL",
            [
                "Cash payment",
                "Cash receipt",
                "Payment through non-account payee cheque",
                "Receipt through non-account payee cheque",
                "Transfer of asset",
                "Transfer of liability",
                "Conversion of assets",
                "Conversion of liabilities",
                "Journal entry debit",
                "Journal entry credit",
                "Other mode debit",
                "Other mode credit",
            ],
            strict=True,
        )
    )
    body = {
        "id": identifier,
        "country": "IN",
        "category": "india-tax-audit",
        "kind": "form26-index",
        "title": f"Form 26 published-field evidence inventory — Part {part}",
        "report_part": part,
        "allow_not_applicable": True,
        "not_applicable_keys": [f["key"] for f in fields if not f["mandatory"]],
        "layout": "published-semantic-fields-and-schedule-cells",
        "scope_label": "Published-field evidence inventory; repeated populations and calculations need independently reviewed workpapers",
        "source_url": FORM_26_PUBLISHED,
        "selection_sources": [FORM_26_RULE, FORM_26_PUBLISHED],
        "source_version": "Archived 33-page original; whole-document visual inventory October 2026; professional qualification pending",
        "source_capture_status": "ORIGINAL_PDF_ARCHIVED_WHOLE_DOCUMENT_VISUAL_INVENTORY_UNQUALIFIED",
        "source_status": "Explicit semantic mapping against original pages, with unresolved source conflicts retained",
        "original_pdf": {
            "path": "docs/country-workflows/legal-sources/IN-Form-26-2026.pdf",
            "sha256": SOURCE_SHA,
            "page_count": 33,
            "professional_approval": False,
        },
        "fields": fields,
        "inventory_counts": {
            "requirements": len(fields),
            "source_fields": sum(f["entry_kind"] == "SOURCE_FIELD" for f in fields),
            "population_controls": sum(f["entry_kind"] == "POPULATION_CONTROL" for f in fields),
            "source_review_controls": sum(
                f["entry_kind"] == "SOURCE_REVIEW_CONTROL" for f in fields
            ),
        },
        "visual_inventory_pages": list(range(1, 34)),
        "transaction_codes_note_8": {
            "page": 13,
            "values": transaction_codes,
            "automatically_classified": False,
        },
        "field_mapping_professionally_qualified": False,
        "requirements": [
            {
                "key": f["key"],
                "title": f["title"],
                "disposition": "UNASSESSED",
                "source_required": True,
                "basis": f"Assess published page {f['page']} / semantic {f['semantic_reference']} against current reviewed workpapers; complete population required for repeated columns",
            }
            for f in fields
        ],
        "statutory_completeness_qualified": False,
        "limitations": [
            "Evidence inventory only: no official filling, calculation engine, statutory opinion, UDIN, signature or filing",
            "Printed rate/percentage/formula labels are source descriptions, not adopted legal rates or automated calculations",
            "Repeated columns require complete populations and source reconciliation; one sample is insufficient for a full-population declaration",
            "Source category, income-numbering and column/cross-reference conflicts require explicit independent professional assessment",
            "Part A/1 and B/1 are distinct retained 65-item presets; no saved report is upgraded automatically",
            "Real-client and professional/legal qualification remain open",
        ],
    }
    return {**body, "sha256": fingerprint(body)}
