"""Deterministic evidence comparisons. Expected dues are inputs, not inferred law."""

import hashlib
import unicodedata
from collections import defaultdict
from datetime import date
from decimal import Decimal, localcontext
from typing import Any

from app.modules.country_workflows.audit_calculations import AUDIT_CALCULATORS
from app.modules.country_workflows.catalogue import OPTIONAL_ROLES, WORKFLOWS, country_guidance
from app.modules.country_workflows.diligence_calculations import DILIGENCE_CALCULATORS
from app.modules.country_workflows.obligation_scope import scope_key
from app.modules.country_workflows.operations import OPERATION_CALCULATORS
from app.modules.country_workflows.payroll_calculations import PAYROLL_CALCULATORS
from app.modules.country_workflows.pension_calculations import PENSION_CALCULATORS
from app.modules.country_workflows.practice_calculations import PRACTICE_CALCULATORS
from app.modules.country_workflows.sector_calculations import SECTOR_CALCULATORS
from app.modules.country_workflows.withholding_calculations import withholding
from app.modules.intelligence.matching import reconcile_transactions


def document_key(value):
    return "".join(
        ch for ch in unicodedata.normalize("NFKC", str(value)).casefold() if ch.isalnum()
    )


def matching_token(value):
    normalized = document_key(value)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else ""


def amount(row, key="amount"):
    return Decimal(str(row[key]))


def unique(rows, key):
    result = {}
    for row in rows:
        value = key(row)
        if value in result:
            raise ValueError(
                "Duplicate domain key; select one corrected source version or aggregate explicitly"
            )
        result[value] = row
    return result


def bank(data, tables):
    from app.modules.country_workflows.bank_dates import date_details

    left, right = tables["books"], tables["statement"]
    transaction_dates = [
        {"source_role": role, "source_row_id": row["id"], **date_details(row)}
        for role in ("books", "statement")
        for row in tables[role]
    ]
    uncertain_dates = sum(row["booking_date_review_required"] for row in transaction_dates)
    for row in [*left, *right]:
        if row["account"] != data.account or row["currency"] != data.currency:
            raise ValueError("Bank BRS requires a single selected account and currency")
        if date.fromisoformat(row["date"]) > data.as_of:
            raise ValueError("Statement/book transaction is after the reconciliation date")

    # The shared matcher historically normalizes ASCII. Supply stable Unicode-aware
    # tokens, retaining the original source text in the saved table and output rows.
    def match_rows(rows):
        return [
            {
                **r,
                "reference": matching_token(r["reference"]),
                "counterparty": matching_token(r.get("counterparty", "")),
            }
            for r in rows
        ]

    matches = reconcile_transactions(
        match_rows(left), match_rows(right), data.tolerance, data.date_tolerance, 3
    )
    book_movement = sum((amount(r) for r in left), Decimal(0))
    bank_movement = sum((amount(r) for r in right), Decimal(0))
    controls = {
        "book_balance_control": data.book_opening + book_movement - data.book_closing,
        "statement_balance_control": data.statement_opening
        + bank_movement
        - data.statement_closing,
        "opening_balance_difference": data.book_opening - data.statement_opening,
    }
    paired_left = {i for m in matches["matches"] for i in m["left_ids"]}
    paired_right = {i for m in matches["matches"] for i in m["right_ids"]}
    unmatched_left = [r for r in left if r["id"] not in paired_left]
    unmatched_right = [r for r in right if r["id"] not in paired_right]
    adjusted = (
        data.book_closing
        + sum((amount(r) for r in unmatched_right), Decimal(0))
        - sum((amount(r) for r in unmatched_left), Decimal(0))
    )
    controls["unexplained_bridge_residual"] = data.statement_closing - adjusted
    rows: list[dict[str, Any]] = []
    for side, rows_ in [("books", unmatched_left), ("statement", unmatched_right)]:
        for r in rows_:
            age = (data.as_of - date.fromisoformat(r["date"])).days
            rows.append(
                {
                    "id": side + ":" + r["id"],
                    "source_id": r["id"],
                    **date_details(r),
                    "side": side,
                    "reference": r["reference"],
                    "amount": r["amount"],
                    "currency": r["currency"],
                    "age_days": age,
                    "stale": age > data.stale_days,
                    "cause": "UNPRESENTED_PAYMENT_CANDIDATE"
                    if side == "books" and amount(r) < 0
                    else "UNCREDITED_DEPOSIT_CANDIDATE"
                    if side == "books"
                    else "UNBOOKED_BANK_ITEM",
                    "state": "EXCEPTION",
                    "cause_status": "REQUIRES_EVIDENCE",
                }
            )
    return {
        "rows": rows,
        "matches": matches["matches"],
        "ambiguous": matches["ambiguous"],
        **{
            key: matches[key]
            for key in (
                "matching_contract",
                "candidate_checks",
                "candidate_check_limit",
                "ambiguity_link_count",
            )
        },
        "control_comparison": {k: str(v) for k, v in controls.items()},
        "adjusted_book_balance": str(adjusted),
        "transaction_dates": transaction_dates,
        "booking_date_review_count": uncertain_dates,
        "blocked": any(v != 0 for v in controls.values()) or bool(uncertain_dates),
        "exception_count": len(rows) + uncertain_dates,
        "limitations": [
            "Bridge explains arithmetic differences only; proposed causes need supporting evidence",
            "Declared opening/closing controls require independent source review",
            "Value dates are retained separately; fallback dates require booking-date evidence before approval",
        ],
    }


def tax_documents(data, tables, right_role="return"):
    def key(r):
        return (
            r["registration"].strip().upper(),
            r["counterparty"].strip().upper(),
            document_key(r["reference"]),
            r["document_type"],
            r["component"].upper(),
            r["currency"],
        )

    for source_rows in tables.values():
        for r in source_rows:
            if not document_key(r["reference"]):
                raise ValueError("Document reference must contain letters or numbers")
            if date.fromisoformat(r["date"]) > data.as_of:
                raise ValueError("Tax document dated after reconciliation date")
            if r["period"] > data.as_of.strftime("%Y-%m"):
                raise ValueError("Tax document reporting period is after reconciliation date")

    def tax_population(population):
        groups = defaultdict(list)
        for row in population:
            groups[key(row)].append(row)
        resolved = {}
        for domain_key, versions in groups.items():
            if len(versions) == 1:
                resolved[domain_key] = versions[0]
                continue
            if not any(row.get("source_review_reasons") for row in versions):
                raise ValueError(
                    "Duplicate domain key; select one corrected source version or aggregate explicitly"
                )
            # Keep every amount/version visible. Neither the first record nor a
            # sum is treated as a resolved current invoice or a credit movement.
            resolved[domain_key] = {
                **versions[0],
                "id": None,
                "amounts_available": False,
                "net_available": False,
                "native_zero_component": False,
                "source_review_reasons": sorted(
                    {
                        "MULTIPLE_SOURCE_VERSIONS_REQUIRE_RESOLUTION",
                        *(
                            reason
                            for row in versions
                            for reason in row.get("source_review_reasons", [])
                        ),
                    }
                ),
                "version_source_ids": [row["id"] for row in versions],
                "source_versions": [
                    {
                        field: row.get(field)
                        for field in (
                            "id",
                            "source_section",
                            "date",
                            "period",
                            "net",
                            "tax",
                            "original_reference",
                            "original_date",
                        )
                    }
                    for row in versions
                ],
            }
        return resolved

    books, portal = (tax_population(tables[role]) for role in ["books", right_role])
    document_groups = []
    for population in (books, portal):
        grouped = defaultdict(list)
        for domain_key, record in population.items():
            grouped[domain_key[:4] + domain_key[5:]].append(record)
        document_groups.append(grouped)

    def absent_native_zero(record, opposite, domain_key):
        # A present document's omitted zero head is not a missing invoice. Only a
        # native, explicitly checked zero qualifies; canonical absence alone does not.
        if (
            not record
            or record.get("native_zero_component") is not True
            or amount(record, "tax") != 0
            or record.get("source_review_reasons")
            or record.get("net_available") is False
        ):
            return False
        others = opposite.get(domain_key[:4] + domain_key[5:], [])
        return (
            bool(others)
            and record["status"] == "active"
            and all(
                other["status"] == "active"
                and not other.get("source_review_reasons")
                and other.get("net_available") is not False
                and other["date"] == record["date"]
                and other["period"] == record["period"]
                and abs(amount(other, "net") - amount(record, "net")) <= data.tolerance
                for other in others
            )
        )

    rows: list[dict[str, Any]] = []
    for index, k in enumerate(sorted(books.keys() | portal.keys()), 1):
        left, right = books.get(k), portal.get(k)
        delta = amount(left, "tax") - amount(right, "tax") if left and right else None
        if any(row and row.get("amounts_available") is False for row in (left, right)):
            delta = None
        base_delta = amount(left, "net") - amount(right, "net") if left and right else None
        if any(row and row.get("net_available") is False for row in (left, right)):
            base_delta = None
        source_reasons = sorted(
            {
                reason
                for row in (left, right)
                if row
                for reason in row.get("source_review_reasons", [])
            }
        )
        explicit_zero = (not right and absent_native_zero(left, document_groups[1], k)) or (
            not left and absent_native_zero(right, document_groups[0], k)
        )
        if explicit_zero:
            delta = base_delta = Decimal(0)
        state = (
            "SOURCE_DOCUMENT_REVIEW_REQUIRED"
            if source_reasons
            else "MATCHED"
            if explicit_zero
            else "BOOKS_ONLY"
            if not right
            else ("INVOICE_ONLY" if right_role == "invoices" else "RETURN_ONLY")
            if not left
            else "SOURCE_STATUS_PENDING"
            if right["status"] == "pending"
            else ("SOURCE_INVOICE_REJECTED" if right_role == "invoices" else "REJECTED_ON_RETURN")
            if right["status"] == "rejected"
            else "SOURCE_STATUS_PENDING"
            if left["status"] != "active"
            else "PERIOD_DIFFERENCE"
            if left["period"] != right["period"]
            else "DATE_DIFFERENCE"
            if left["date"] != right["date"]
            else "MATCHED"
            if delta is not None
            and base_delta is not None
            and abs(delta) <= data.tolerance
            and abs(base_delta) <= data.tolerance
            else "VARIANCE"
        )
        rows.append(
            {
                "id": f"doc-{index}",
                "registration": k[0],
                "counterparty": k[1],
                "reference": (left or right)["reference"],
                "document_type": k[3],
                "component": k[4],
                "currency": k[5],
                "state": state,
                "books_id": left["id"] if left else None,
                right_role + "_id": right["id"] if right else None,
                "books_tax": left["tax"] if left and left.get("amounts_available", True) else None,
                right_role + "_tax": right["tax"]
                if right and right.get("amounts_available", True)
                else None,
                "books_version_source_ids": left.get("version_source_ids", [left["id"]])
                if left
                else [],
                right_role + "_version_source_ids": right.get("version_source_ids", [right["id"]])
                if right
                else [],
                "books_source_versions": left.get("source_versions") if left else None,
                right_role + "_source_versions": right.get("source_versions") if right else None,
                "tax_difference": str(delta) if delta is not None else None,
                "net_difference": str(base_delta) if base_delta is not None else None,
                "books_period": left["period"] if left else None,
                right_role + "_period": right["period"] if right else None,
                "legal_credit_eligibility": "NOT_DETERMINED",
                "source_review_reasons": source_reasons,
                "books_source_section": left.get("source_section") if left else None,
                right_role + "_source_section": right.get("source_section") if right else None,
                "source_itc_availability": right.get("source_itc_availability") if right else None,
                "source_ims_status": right.get("source_ims_status") if right else None,
                "comparison_basis": "EXPLICIT_NATIVE_ZERO_COMPONENT_WITH_OPPOSITE_DOCUMENT_PRESENT"
                if explicit_zero
                else "DIRECT_COMPONENT_COMPARISON",
            }
        )
    totals: defaultdict[str, defaultdict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for role in ["books", right_role]:
        for r in tables[role]:
            partition = "|".join(
                [r["registration"].upper(), r["period"], r["component"].upper(), r["currency"]]
            )
            totals[partition][role + "_tax"] += amount(r, "tax")
    return {
        **(
            {
                "invoice_evidence_scope": {
                    "direction": data.invoice_direction,
                    "filing_status": "NOT_ASSESSED_BY_INVOICE_COMPARISON",
                    "irp_authenticity": "NOT_VERIFIED",
                }
            }
            if right_role == "invoices"
            else {}
        ),
        "rows": rows,
        "totals": {
            k: {s: str(v) for s, v in values.items()} for k, values in sorted(totals.items())
        },
        "totals_basis": "SOURCE_DOCUMENT_TAX_FIELDS_NOT_RESOLVED_CREDIT_OR_FILING_VALUES",
        "exception_count": sum(r["state"] != "MATCHED" for r in rows),
        "blocked": False,
        "limitations": [
            "Canonical document comparison only; native government export adapters are not qualified",
            "No input-credit eligibility, reverse-charge liability, interest or filing conclusion is calculated",
            "UAE VAT returns contain aggregates; do not represent them as a supplier-matching portal",
            "Invoice evidence does not establish filed GST returns, IRP authenticity or complete book population"
            if right_role == "invoices"
            else "Canonical return documents require independently prepared document schedules",
        ],
    }


def obligations(data, tables, country):
    roles = list(WORKFLOWS[data.workflow][2])
    expected_role = roles[0]
    groups: dict[str, defaultdict[tuple, dict[str, Any]]] = {}
    forbidden = {"PF", "ESI", "PT", "TDS", "TCS"} if country == "AE" else set()
    for role, source in tables.items():
        grouped: defaultdict[tuple, dict[str, Any]] = defaultdict(
            lambda: {
                "amount": Decimal(0),
                "ids": [],
                "late": False,
                "unknown_due": False,
                "due_dates": set(),
                "payment_dates": [],
            }
        )
        for r in source:
            component = r["component"].upper()
            if component.split(":")[0] in forbidden:
                raise ValueError("Indian domestic statutory component cannot run in a UAE workflow")
            if component == "TCS:206C(1H)" and r["period"] >= "2025-04":
                raise ValueError(
                    "Section206C(1H) is withdrawn for this period; select a qualified applicable obligation"
                )
            if (
                role in {"payment", "channel", "bank"}
                and r.get("payment_date")
                and date.fromisoformat(r["payment_date"]) > data.as_of
            ):
                raise ValueError("Future payment cannot settle the current reconciliation")
            if r["period"] > data.as_of.strftime("%Y-%m"):
                raise ValueError(
                    "Future obligation period cannot settle the current reconciliation"
                )
            if r["amount"].startswith("-"):
                raise ValueError(
                    "Corrected obligation sources must be restated; negative settlements require a qualified allocation adapter"
                )
            k = (
                r["registration"].upper(),
                r["subject"].upper(),
                r["period"],
                component,
                r["currency"],
                scope_key(r),
            )
            g = grouped[k]
            g["pension_scope"] = r.get("pension_scope")
            g["amount"] += amount(r)
            g["ids"].append(r["id"])
            if r.get("due_date"):
                g["due_dates"].add(r["due_date"])
            if r.get("payment_date"):
                g["payment_dates"].append(r["payment_date"])
            if role == expected_role:
                g["unknown_due"] |= not r.get("due_date")
            if role in {"payment", "bank"}:
                g["unknown_due"] |= not r.get("due_date") or not r.get("payment_date")
                g["late"] |= bool(
                    r.get("due_date")
                    and r.get("payment_date")
                    and r["payment_date"] > r["due_date"]
                )
        groups[role] = grouped
    keys = sorted(set().union(*(g.keys() for g in groups.values())))
    rows: list[dict[str, Any]] = []
    for index, k in enumerate(keys, 1):
        present = {role: groups[role].get(k) for role in roles}
        missing = [role for role, value in present.items() if value is None]
        amounts = {role: str(value["amount"]) if value else None for role, value in present.items()}
        expected = present[expected_role]
        expected_dates = expected["due_dates"] if expected else set()
        payment_roles = [role for role in roles if role in {"bank", "payment"}]
        inconsistent_due_dates = any(
            value and value["due_dates"] and value["due_dates"] != expected_dates
            for role, value in present.items()
            if role in payment_roles
        )
        late_from_expected = len(expected_dates) == 1 and any(
            when > next(iter(expected_dates))
            for role in payment_roles
            if present[role]
            for when in (present[role] or {})["payment_dates"]
        )
        state = (
            "MISSING_SOURCE_PARTITION"
            if missing
            else "VARIANCE"
            if any(
                abs(value["amount"] - expected["amount"]) > data.tolerance
                if value is not None and expected is not None
                else False
                for value in present.values()
            )
            else "DUE_DATE_ALLOCATION_REQUIRED"
            if len(expected_dates) > 1
            else "DUE_DATE_DIFFERENCE"
            if inconsistent_due_dates
            else "LATE_PAYMENT"
            if late_from_expected
            else "TIMING_NOT_VERIFIED"
            if any(v["unknown_due"] for v in present.values() if v is not None)
            else "MATCHED"
        )
        rows.append(
            {
                "id": f"obligation-{index}",
                "registration": k[0],
                "subject": k[1],
                "period": k[2],
                "component": k[3],
                "currency": k[4],
                "state": state,
                "amounts": amounts,
                **(
                    {
                        "pension_scope": next(
                            value["pension_scope"]
                            for value in present.values()
                            if value and value.get("pension_scope")
                        )
                    }
                    if k[5]
                    else {}
                ),
                "source_ids": {
                    role: value["ids"] if value else [] for role, value in present.items()
                },
                "missing_roles": missing,
                "liability_calculation": "DECLARED_INPUT_NOT_LEGAL_COMPUTATION",
            }
        )
    return {
        "rows": rows,
        "exception_count": sum(r["state"] != "MATCHED" for r in rows),
        "blocked": data.workflow == "india-withholding",
        "limitations": [
            *(
                [
                    "Legacy aggregate withholding preview cannot be approved: regenerate using explicit deductor/collector liability or deductee/collectee credit records"
                ]
                if data.workflow == "india-withholding"
                else []
            ),
            "Declared expected amounts and due dates require independent professional validation",
            "This compares sources; it does not compute statutory contributions, salary tax or benefit entitlement",
            "Due dates must be the obligation due dates, not bank processing dates; no deadline is inferred",
        ],
    }


def vat_return(data, tables):
    from app.modules.country_workflows.vat201_layouts import EMIRATES, LAYOUTS, validate_comparison

    validate_comparison(data, tables)

    def key(r):
        return (
            r["registration"].upper(),
            r["period_start"],
            r["period_end"],
            r["box"],
            r["currency"],
        )

    included = {
        role: [
            row
            for row in population
            if not data.restrict_to_required_boxes or row["box"] in data.required_boxes
        ]
        for role, population in tables.items()
    }
    excluded = [
        {
            "source_role": role,
            "source_row_id": row["id"],
            **{
                field: row[field]
                for field in (
                    "registration",
                    "period_start",
                    "period_end",
                    "box",
                    "currency",
                    "taxable_amount",
                    "tax",
                    "adjustment",
                )
            },
        }
        for role, population in tables.items()
        for row in population
        if data.restrict_to_required_boxes and row["box"] not in data.required_boxes
    ]

    def controls(population):
        totals: dict[tuple[str, str], dict[str, Any]] = {}
        for row in population:
            total = totals.setdefault(
                (row["source_role"], row["currency"]),
                {
                    "row_count": 0,
                    "taxable_amount": Decimal(0),
                    "tax": Decimal(0),
                    "adjustment": Decimal(0),
                },
            )
            total["row_count"] += 1
            for field in ("taxable_amount", "tax", "adjustment"):
                total[field] += amount(row, field)
        return [
            {
                "source_role": role,
                "currency": currency,
                **{
                    field: str(value) if field != "row_count" else value
                    for field, value in values.items()
                },
            }
            for (role, currency), values in sorted(totals.items())
        ]

    filed = unique(included["return"], key)
    books: defaultdict[tuple, dict[str, Any]] = defaultdict(
        lambda: {
            "taxable_amount": Decimal(0),
            "tax": Decimal(0),
            "adjustment": Decimal(0),
            "ids": [],
        }
    )
    for r in included["books"]:
        group = books[key(r)]
        for field in ["taxable_amount", "tax", "adjustment"]:
            group[field] += amount(r, field)
        group["ids"].append(r["id"])
    scopes = {key(r)[:3] + (r["currency"],) for rows in tables.values() for r in rows}
    if not scopes:
        raise ValueError(
            "A nil VAT return needs explicit period/registration box rows; missing return boxes are not a nil return"
        )
    if any(date.fromisoformat(end) > data.as_of for registration, start, end, currency in scopes):
        raise ValueError("Return period extends beyond the reconciliation date")
    keys = {
        (registration, start, end, box, currency)
        for registration, start, end, currency in scopes
        for box in data.required_boxes
    }
    keys.update(books)
    keys.update(filed)
    rows = []
    if data.vat201_layout == "custom":
        ordered_keys = sorted(keys)
    else:
        order = {box: index for index, box in enumerate(LAYOUTS[data.vat201_layout]["boxes"])}
        ordered_keys = sorted(keys, key=lambda k: k[:3] + (order[k[3]], k[4]))
    for index, k in enumerate(ordered_keys, 1):
        b, r = books.get(k), filed.get(k)
        deltas = {
            field: str(b[field] - amount(r, field)) if b and r else None
            for field in ["taxable_amount", "tax", "adjustment"]
        }
        state = (
            "MISSING_BOX_EVIDENCE"
            if not b and not r
            else "BOOKS_ONLY"
            if not r
            else "RETURN_ONLY"
            if not b
            else "MATCHED"
            if all(v is not None and abs(Decimal(v)) <= data.tolerance for v in deltas.values())
            else "VARIANCE"
        )
        rows.append(
            {
                "id": f"box-{index}",
                "registration": k[0],
                "period_start": k[1],
                "period_end": k[2],
                "box": k[3],
                **({"emirate": EMIRATES[k[3]]} if k[3] in EMIRATES else {}),
                "currency": k[4],
                "state": state,
                "differences": deltas,
                "book_source_ids": b["ids"] if b else [],
                "return_source_id": r["id"] if r else None,
            }
        )
    return {
        "rows": rows,
        "exception_count": sum(r["state"] != "MATCHED" for r in rows),
        "blocked": any(
            r["state"] == "MISSING_BOX_EVIDENCE"
            or (data.vat201_layout != "custom" and r["state"] in {"BOOKS_ONLY", "RETURN_ONLY"})
            for r in rows
        ),
        "vat201_layout": data.vat201_layout,
        "box_comparison_scope": {
            "mode": "SELECTED_REQUIRED_BOXES"
            if data.restrict_to_required_boxes
            else "ALL_RETAINED_BOXES",
            "required_boxes": data.required_boxes,
            "assessment": data.box_scope_assessment.strip()
            if data.restrict_to_required_boxes
            else None,
            "included_rows": {role: len(population) for role, population in included.items()},
            "excluded_rows": {
                role: len(population) - len(included[role]) for role, population in tables.items()
            },
            "whole_return_completeness": "NOT_DETERMINED",
        },
        "excluded_box_rows": excluded,
        "excluded_box_controls": controls(excluded),
        "included_box_controls": controls(
            [
                {**row, "source_role": role}
                for role, population in included.items()
                for row in population
            ]
        ),
        "limitations": [
            "Selected-box comparison excludes only explicitly assessed box populations; no whole-return completeness conclusion is determined"
            if data.restrict_to_required_boxes
            else "All retained boxes are compared; source-file completeness is not whole-return completeness",
            "VAT201 box assignments and required-box scope must be independently assessed",
            "Taxable amounts, tax and adjustments compare separately; no tax rate or recovery entitlement is inferred",
            "Canonical source contracts do not imply a live FTA connection or native VAT201 parser",
        ],
    }


def inventory(data, tables):
    def key(r):
        return (r["site"], r["sku"], r["uom"], r["currency"], r.get("lot", ""))

    books, counts = (unique(tables[role], key) for role in ["books", "count"])
    rows: list[dict[str, Any]] = []
    total = covered = Decimal(0)
    for index, k in enumerate(sorted(books.keys() | counts.keys()), 1):
        b, c = books.get(k), counts.get(k)
        for r in [r for r in [b, c] if r]:
            if date.fromisoformat(r["count_date"]) > data.as_of:
                raise ValueError(
                    "Future inventory evidence requires a separately qualified roll-back procedure"
                )
        variance = amount(c, "quantity") - amount(b, "quantity") if b and c else None
        carrying = amount(b, "quantity") * amount(b, "unit_cost") if b else None
        valuation = (
            None
            if not b or b["unit_nrv"] is None
            else max(Decimal(0), amount(b, "unit_cost") - amount(b, "unit_nrv"))
            * max(Decimal(0), amount(b, "quantity"))
        )
        aligned = bool(b and c and b["count_date"] == c["count_date"] == data.as_of.isoformat())
        state = (
            "BOOKS_ONLY"
            if not c
            else "COUNT_ONLY"
            if not b
            else "COUNT_DATE_BRIDGE_REQUIRED"
            if not aligned
            else "OWNERSHIP_UNCONFIRMED"
            if any(r["ownership"] != "owned" for r in [b, c])
            else "CONDITION_EXCEPTION"
            if c["condition"] != "good"
            else "NEGATIVE_QUANTITY"
            if amount(b, "quantity") < 0 or amount(c, "quantity") < 0
            else "VALUATION_INPUT_MISSING"
            if b["unit_nrv"] is None
            else "VARIANCE"
            if variance != 0
            else "NRV_WRITEDOWN"
            if valuation is not None and valuation > 0
            else "MATCHED"
        )
        if carrying is not None:
            total += abs(carrying)
            if aligned and c["ownership"] == b["ownership"] == "owned":
                covered += min(abs(amount(c, "quantity")), abs(amount(b, "quantity"))) * amount(
                    b, "unit_cost"
                )
        rows.append(
            {
                "id": f"stock-{index}",
                "site": k[0],
                "sku": k[1],
                "lot": k[4],
                "uom": k[2],
                "currency": k[3],
                "state": state,
                "quantity_difference": str(variance) if variance is not None else None,
                "carrying_value": str(carrying) if carrying is not None else None,
                "potential_nrv_writedown": str(valuation) if valuation is not None else None,
                "books_id": b["id"] if b else None,
                "count_id": c["id"] if c else None,
            }
        )
    # Monetary coverage across currencies must not be aggregated.
    currencies = {k[3] for k in books}
    return {
        "rows": rows,
        "exception_count": sum(r["state"] != "MATCHED" for r in rows),
        "blocked": False,
        "coverage": {
            "basis": "Book monetary value supported by aligned uploaded counts; not physical verification",
            "book_value": str(total) if len(currencies) == 1 else None,
            "count_supported_value": str(covered) if len(currencies) == 1 else None,
            "percent": str(covered / total * 100) if total and len(currencies) == 1 else None,
        },
        "limitations": [
            "No physical attendance, ownership assurance or drawing-power calculation is implied",
            "Counts before reporting date require a separately evidenced movement bridge",
        ],
    }


def checks(data, tables):
    supplied = unique(tables["checks"], lambda r: (r["subject"], r["requirement"]))
    subjects = sorted(data.subjects)
    if any(r["subject"] not in subjects for r in tables["checks"]):
        raise ValueError("Evidence includes subjects outside the declared population")
    rows: list[dict[str, Any]] = []
    for subject in subjects:
        for requirement in data.required_checks:
            r = supplied.get((subject, requirement))
            state = (
                "MISSING"
                if not r
                else "EXPIRED"
                if r.get("expires_on") and date.fromisoformat(r["expires_on"]) < data.as_of
                else "EVIDENCE_MISSING"
                if r["state"] in {"supported", "exception"} and not r["evidence_reference"]
                else "RATIONALE_MISSING"
                if r["state"] == "not-applicable" and not r["rationale"]
                else r["state"].upper()
            )
            rows.append(
                {
                    "id": f"check-{len(rows) + 1}",
                    "subject": subject,
                    "requirement": requirement,
                    "state": state,
                    "source_id": r["id"] if r else None,
                    "evidence_reference": r["evidence_reference"] if r else None,
                    "rationale": r["rationale"] if r else None,
                }
            )
    extra = [r["id"] for r in supplied.values() if r["requirement"] not in data.required_checks]
    return {
        "rows": rows,
        "out_of_scope_source_ids": extra,
        "exception_count": sum(r["state"] not in {"SUPPORTED", "NOT-APPLICABLE"} for r in rows),
        "blocked": any(
            r["state"] in {"MISSING", "EVIDENCE_MISSING", "RATIONALE_MISSING", "EXPIRED"}
            for r in rows
        ),
        "limitations": [
            "Evidence references are declared references, not verified external registry responses",
            "No automatic sanctions clearance, legal eligibility or professional attestation is issued",
            "Requirement scope is engagement-specific and must be independently assessed",
        ],
    }


def calculate(
    data,
    country,
    sources,
    *,
    bank_account_review=None,
    import_nil_receipt=None,
    esic_population_review=None,
):
    title, countries, roles = WORKFLOWS[data.workflow]
    if countries and country not in countries:
        raise ValueError("Workflow is unavailable for this engagement country")
    optional_roles = OPTIONAL_ROLES.get(data.workflow, {})
    if not set(roles) <= set(sources) or not set(sources) <= (set(roles) | set(optional_roles)):
        raise ValueError("Select every required source role exactly once")
    roles = {**roles, **{role: kind for role, kind in optional_roles.items() if role in sources}}
    account_scope = None
    if bank_account_review is not None:
        from app.modules.country_workflows.bank_binding import bind

        sources, account_scope = bind(data, country, sources, *bank_account_review)
    for role, table in sources.items():
        if table.get("parser_version") == "withholding-obligations/1" and (
            role not in table.get("allowed_source_roles", [])
            or table.get("native_metadata", {}).get("controls", {}).get("cutoff_date")
            != data.as_of.isoformat()
        ):
            raise ValueError(
                "Withholding obligation purpose and cutoff must match the allocation review"
            )
        if table.get("allowed_workflows") and data.workflow not in table["allowed_workflows"]:
            raise ValueError("Derived source is restricted to its assessed target workflows")
        if (
            any(row.get("withholding_scope") for row in table["rows"])
            and data.workflow != "obligation-bank-allocations"
        ):
            raise ValueError(
                "Transaction-scoped withholding obligations require the bank allocation workflow"
            )
        if table.get("native_format") == "india-gstr1-document-series-json" and (
            data.workflow != "india-document-series" or role != "reported"
        ):
            raise ValueError(
                "Native document series can establish only the reported role of India document-series comparison"
            )
        if table.get("parser_version") == "bank-clearance-carryforward/1" and (
            data.workflow != "bank-subsequent-clearance" or role != "outstanding"
        ):
            raise ValueError(
                "Carried bank residuals can establish only the outstanding role of subsequent clearance"
            )
        if table.get("native_format") == "india-gstr1-documents-json" and (
            data.workflow != "india-gstr1-documents" or role != "return"
        ):
            raise ValueError(
                "Native GSTR-1 invoices/notes may supply only the outward reconciliation return role"
            )
        if table.get("native_format") == "india-gstr1-summary-json" and (
            data.workflow != "india-gstr1-summary" or role != "return"
        ):
            raise ValueError(
                "Native GSTR-1 summary can supply only the return role of summary reconciliation"
            )
        if table.get("native_format") == "india-inv01-json":
            if (data.workflow, role) not in {
                ("india-gst", "books"),
                ("india-invoice-register", "invoices"),
                ("india-gstr1-documents", "books"),
            }:
                raise ValueError(
                    "INV-01 supplies invoice evidence, not a filed GST return; use invoices in the register comparison or invoice-supported books against independent return evidence"
                )
            if (
                data.workflow == "india-gstr1-documents"
                and table.get("native_metadata", {}).get("direction") != "sale"
            ):
                raise ValueError(
                    "Outward GSTR-1 books require sales invoice evidence, not purchases"
                )
            if (
                data.workflow == "india-invoice-register"
                and table.get("native_metadata", {}).get("direction") != data.invoice_direction
            ):
                raise ValueError(
                    "Native invoice direction differs from the declared purchase/sale comparison"
                )
        has_arrears = table.get("native_format") == "india-epfo-arrear-ecr-v2" or (
            table.get("table_type") == "obligations"
            and any(row.get("population") == "arrears" for row in table["rows"])
        )
        if has_arrears and not data.arrear_only:
            raise ValueError(
                "Select explicit arrear-only comparison scope; arrears cannot stand in for a complete monthly return"
            )
        if (
            data.arrear_only
            and table.get("table_type") == "obligations"
            and any(row.get("population") != "arrears" for row in table["rows"])
        ):
            raise ValueError(
                "Every expected, reported and payment obligation must be explicitly tagged as an arrear population"
            )
        if table.get("native_format") == "india-epfo-arrear-ecr-v2" and data.currency != "INR":
            raise ValueError(
                "Native arrear ECR comparisons require INR; no currency conversion is inferred"
            )
        if table.get("native_format") == "india-epfo-arrear-ecr-v2" and (
            data.workflow,
            role,
        ) not in {
            ("statutory-dues", "return"),
            ("india-payroll-rules", "reported"),
            ("obligation-bank-allocations", "reported"),
        }:
            raise ValueError(
                "Native arrear ECR can establish only an assessed return/reported role, not expected dues or bank payment"
            )
        if (
            data.workflow == "inventory-count-bridge"
            and data.stock_bridge_mode == "bidirectional-controlled"
        ):
            from app.modules.country_workflows.inventory_controls import verify_quantity_controls

            if (
                table.get("inventory_controls_verified") is not True
                or table.get("inventory_quantity_controls") is None
            ):
                raise ValueError(
                    "Controlled inventory bridging requires independent partition quantity controls for every source"
                )
            verify_quantity_controls(table["rows"], table["inventory_quantity_controls"])
        if data.workflow == "procurement-match" and role != "payments":
            from app.modules.country_workflows.purchase_controls import verify as verify_purchase

            if (
                table.get("purchase_controls_verified") is not True
                or table.get("purchase_quantity_controls") is None
            ):
                raise ValueError(
                    "Procurement matching requires independently controlled purchase quantities and explicit units on orders, receipts and invoices"
                )
            verify_purchase(table["rows"], table["purchase_quantity_controls"])
        if (
            table.get("parser_version") == "uae-vat201-composition/1"
            and table.get("native_metadata", {}).get("layout") == "emirate-20"
            and data.vat201_layout != "emirate-20"
        ):
            raise ValueError(
                "Select the explicit twenty-row emirate VAT201 layout for this composed source"
            )
        if table.get("parser_version") == "uae-vat201-composition/1" and (
            data.workflow != "uae-vat-return" or role != "books"
        ):
            raise ValueError(
                "Composed VAT201 sources can establish only books, not filed-return evidence"
            )
        if table.get("native_format") == "india-gstr2b-json" and (
            data.workflow != "india-gst" or role != "return"
        ):
            raise ValueError(
                "Native GSTR-2B can establish only the India GST return role, not independent books"
            )
        if table.get("parser_version") == "contribution-obligations/1" and (
            data.workflow not in {"statutory-dues", "obligation-bank-allocations"}
            or role != "expected"
        ):
            raise ValueError(
                "Derived contribution obligations can establish only expected remittances, not returns or payments"
            )
        # Instruction/return populations are not an independent payroll expectation
        # or evidence that money was settled, even when their totals agree.
        if table.get("native_format") in {
            "uae-wps-sif",
            "uae-wps-sif-evp",
            "india-epfo-ecr",
        } and role not in {
            "channel",
            "return",
            "reported",
        }:
            raise ValueError(
                "Native WPS/ECR files may establish only a return/channel role; "
                "select independent expected dues and confirmed payment evidence"
            )
        if (
            table.get("allowed_source_roles") is not None
            and role not in table["allowed_source_roles"]
        ):
            raise ValueError("Source is restricted to its assessed source roles")
        if table["table_type"] != roles[role] or (
            not table["rows"] and not table.get("nil_reason")
        ):
            raise ValueError("Wrong source type or empty source population")
        if data.workflow == "bank-brs" and table.get("native_format") in {"camt053", "swift-mt940"}:
            native = table["native_metadata"]
            prefix = "book" if role == "books" else "statement"
            if (
                native["account"]
                != (
                    account_scope["original_bank_source_account"]
                    if account_scope is not None and role == account_scope["bank_source_role"]
                    else data.account
                )
                or native["currency"] != data.currency
                or native["through"] != data.as_of.isoformat()
                or Decimal(native["opening"]) != getattr(data, prefix + "_opening")
                or Decimal(native["closing"]) != getattr(data, prefix + "_closing")
            ):
                raise ValueError(
                    "BRS scope and balance controls must agree to the original native bank statement"
                )
    if (
        data.workflow == "india-gst"
        and sources["return"].get("native_format") == "india-gstr2b-json"
        and sources["books"].get("native_format") == "india-inv01-json"
        and sources["books"].get("native_metadata", {}).get("direction") != "purchase"
    ):
        raise ValueError(
            "A sales invoice cannot establish purchase books against an inward GSTR-2B source"
        )
    tables = {role: source["rows"] for role, source in sources.items()}
    esic_links = esic_metadata = None
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        if data.esic_population_review_id is not None:
            from app.modules.country_workflows.esic_binding import bind as bind_esic

            if esic_population_review is None:
                raise ValueError(
                    "Verify the requested ESIC population review before contribution calculation"
                )
            esic_links, esic_metadata = bind_esic(data, tables, *esic_population_review)
        elif esic_population_review is not None:
            raise ValueError("An ESIC population receipt requires an explicit reviewed link")
        if data.workflow == "grant-utilisation":
            from app.modules.country_workflows.grant_utilisation import compare as grant_compare

            result = grant_compare(data, tables, country)
        elif data.workflow == "inventory-custody-confirmations":
            from app.modules.country_workflows.inventory_custody import compare as compare_custody

            result = compare_custody(data, sources)
        elif data.workflow == "party-balance-confirmations":
            from app.modules.country_workflows.party_confirmations import compare as compare_parties

            result = compare_parties(data, sources)
        elif data.workflow == "inventory-valuation-control":
            from app.modules.country_workflows.inventory_valuation import (
                compare as compare_inventory_values,
            )

            result = compare_inventory_values(data, sources)
        elif data.workflow == "india-esic-population":
            from app.modules.country_workflows.esic_population import compare as compare_esic

            result = compare_esic(data, tables)
        elif data.workflow == "bank-account-evidence":
            from app.modules.country_workflows.bank_accounts import compare

            result = compare(data, tables, country)
        elif data.workflow == "payroll-ledger-rollforward":
            from app.modules.country_workflows.payroll_ledger import reconcile

            result = reconcile(data, tables, country)
        elif data.workflow == "obligation-bank-allocations":
            from app.modules.country_workflows.dues_allocations import allocate

            if (
                sources["bank"].get("native_format") in {"camt053", "swift-mt940"}
                and data.bank_payment_sign != "debit-negative"
            ):
                raise ValueError(
                    "Native bank outflows use debit-negative amounts; credits cannot settle obligations"
                )
            result = allocate(data, tables, country)
        elif data.workflow in {"india-withholding-liability", "india-withholding-credit"}:
            result = withholding(data, tables)
        elif data.workflow in OPERATION_CALCULATORS:
            result = OPERATION_CALCULATORS[data.workflow](data, tables)
        elif data.workflow in PENSION_CALCULATORS:
            result = PENSION_CALCULATORS[data.workflow](data, tables)
        elif data.workflow in PAYROLL_CALCULATORS:
            result = PAYROLL_CALCULATORS[data.workflow](data, tables)
        elif data.workflow in AUDIT_CALCULATORS:
            result = AUDIT_CALCULATORS[data.workflow](data, tables)
        elif data.workflow in PRACTICE_CALCULATORS:
            result = PRACTICE_CALCULATORS[data.workflow](data, tables)
        elif data.workflow == "uae-import-vat":
            from app.modules.country_workflows.import_vat import import_vat

            result = import_vat(data, tables, nil_receipt=import_nil_receipt)
        elif data.workflow in SECTOR_CALCULATORS:
            result = SECTOR_CALCULATORS[data.workflow](data, tables)
        elif data.workflow in DILIGENCE_CALCULATORS:
            result = DILIGENCE_CALCULATORS[data.workflow](data, tables, country)
        elif data.workflow == "bank-brs":
            result = bank(data, tables)
        elif data.workflow == "india-document-series":
            from app.modules.country_workflows.document_series import compare as compare_series

            result = compare_series(data, tables)
        elif data.workflow == "india-gstr1-summary":
            from app.modules.country_workflows.gst_summary import compare_summary

            result = compare_summary(data, tables)
        elif data.workflow == "india-invoice-register":
            result = tax_documents(data, tables, "invoices")
        elif data.workflow in {"uae-vat", "india-gst", "india-gstr1-documents"}:
            if data.workflow == "india-gstr1-documents" and data.currency != "INR":
                raise ValueError("Outward GSTR-1 reconciliation requires INR")
            result = tax_documents(data, tables)
            if data.workflow == "india-gstr1-documents":
                from app.modules.country_workflows.india_gstr1_source import month_end

                if any(
                    month_end(row["period"]) > data.as_of
                    for population in tables.values()
                    for row in population
                ):
                    raise ValueError(
                        "Outward GSTR-1 reporting month extends beyond the reconciliation date"
                    )
                result["blocked"] = any(row["source_review_reasons"] for row in result["rows"])
                native = sources["return"].get("native_metadata", {})
                result["outward_gst_scope"] = {
                    key: native.get(key)
                    for key in (
                        "supplier_gstin",
                        "return_period",
                        "declared_section_controls",
                        "context_evidence_version_id",
                        "context_sha256",
                        "retrieval_scope_assessment",
                        "source_population_scope",
                    )
                }
                result["outward_gst_scope"]["filing_status"] = (
                    "NOT_ESTABLISHED_BY_DOCUMENT_COMPARISON"
                )
                result["limitations"] = [
                    "Declared outward invoice/note sections only; aggregated B2CS, advances, HSN and full-return completeness require separate evidence",
                    "Amendments, source status/de-link flags and unexplained invoice-value differences require corrected source populations before approval",
                    "Unregistered/export category keys represent declared reporting categories, not verified customer identities",
                    "Retained request context is independently assessed, not machine-authenticated GSTIN, period, provider, IRP or filing proof",
                ]

        elif data.workflow == "uae-vat-return":
            result = vat_return(data, tables)
        elif data.workflow in {"payroll-settlement", "statutory-dues", "india-withholding"}:
            result = obligations(data, tables, country)
        elif data.workflow == "stock-audit":
            result = inventory(data, tables)
        else:
            result = checks(data, tables)
    if esic_links is not None:
        from app.modules.country_workflows.esic_binding import annotate

        result = annotate(result, esic_links, esic_metadata)
    elif data.workflow == "india-payroll-rules" and any(
        row["component"].startswith("ESI:") for row in tables["bases"]
    ):
        result["esic_population_binding"] = {
            "status": "NOT_LINKED",
            "eligibility_status": "ASSESSED_SEPARATELY_NOT_INFERRED_FROM_ESIC_WAGES",
        }
    if data.workflow in {"bank-brs", "bank-subsequent-clearance", "obligation-bank-allocations"}:
        result["bank_account_evidence"] = account_scope or {
            "status": "LINK_REQUESTED_NOT_VERIFIED"
            if data.bank_account_review_id
            else "NOT_LINKED_ARITHMETIC_SCOPE_ONLY",
            "bank_authentication_status": "NOT_ESTABLISHED_BY_DOCUMENT_COMPARISON",
        }
    return {
        **result,
        "title": data.title,
        "workflow": data.workflow,
        "workflow_version": "grant-utilisation-1"
        if data.workflow == "grant-utilisation"
        else "withholding-evidence-1"
        if data.workflow in {"india-withholding-liability", "india-withholding-credit"}
        else "audit-extensions-1"
        if data.workflow
        in {
            *AUDIT_CALCULATORS,
            *OPERATION_CALCULATORS,
            *PRACTICE_CALCULATORS,
            *SECTOR_CALCULATORS,
            *DILIGENCE_CALCULATORS,
            *PAYROLL_CALCULATORS,
            *PENSION_CALCULATORS,
        }
        else "country-workflows-1",
        "as_of": data.as_of.isoformat(),
        "rationale": data.rationale,
        "review_status": "UNVERIFIED",
        "country_guidance": country_guidance(country, data.as_of, data.tax_year_start),
        "statutory_calculation_qualified": False,
        "professional_conclusion": "NOT_DETERMINED",
        "obligation_population_scope": "ARREARS_ONLY_NOT_COMPLETE_MONTHLY_RETURN"
        if data.arrear_only
        else "DECLARED_SOURCE_SCOPE",
        "execution_mode": "deterministic_engine",
        "ml_execution_mode": None,
        "language_model_dependency": False,
        "population_completeness": "UPLOADED_FILE_CONTROLS_ONLY",
        "nil_population": all(not s["rows"] for s in sources.values()),
        "nil_declarations": {
            role: s["nil_reason"] for role, s in sources.items() if s.get("nil_reason")
        },
        "parameters": data.model_dump(mode="json"),
        "source_roles": {
            role: {
                "row_count": len(s["rows"]),
                "control_totals": s["control_totals"],
                "source_range": s.get("source_range"),
                "source_snapshot_id": s.get("source_snapshot_id"),
            }
            for role, s in sources.items()
        },
    }
