"""Normal-sign payroll movements, with directional and separate GL controls."""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, TypedDict

from app.modules.country_workflows.audit_calculations import result


class Group(TypedDict):
    positive: Decimal
    negative: Decimal
    count: int


def reconcile(data, tables, country):
    start = data.period_start
    opening_date = start - timedelta(days=1)
    balances: dict[str, dict[tuple[str, str, str], dict[str, Any]]] = {}
    classes: dict[tuple[str, str, str], str] = {}
    movements: dict[str, defaultdict[tuple, Group]] = {}
    links: list[dict[str, Any]] = []

    def partition(row):
        key = row["registration"], row["account"], row["currency"]
        if key in classes and classes[key] != row["account_class"]:
            raise ValueError(
                "Payroll account class conflicts within the same registration/account/currency"
            )
        classes[key] = row["account_class"]
        return key

    for role in ("opening", "closing"):
        balances[role] = {}
        expected_date = opening_date if role == "opening" else data.as_of
        for row in tables[role]:
            key = partition(row)
            if date.fromisoformat(row["as_of"]) != expected_date:
                raise ValueError(
                    "Payroll GL balance dates must equal the day before period start and the reporting date"
                )
            if key in balances[role]:
                raise ValueError("Duplicate payroll registration/account/currency balance")
            balances[role][key] = row
    for role in ("payroll", "posted"):
        grouped = movements[role] = defaultdict(
            lambda: {"positive": Decimal(0), "negative": Decimal(0), "count": 0}
        )
        seen = set()
        for row in tables[role]:
            key = partition(row)
            if not start <= date.fromisoformat(row["posting_date"]) <= data.as_of:
                raise ValueError("Payroll posting is outside the declared accounting window")
            if country == "AE" and row["component"].upper().split(":")[0] in {
                "PF",
                "ESI",
                "PT",
                "TDS",
                "TCS",
            }:
                raise ValueError(
                    "Indian domestic payroll components cannot be activated in a UAE ledger bridge"
                )
            bucket = key + (row["wage_month"], row["component"], row["category"], row["subject"])
            identity = bucket + (row["reference"], row["posting_date"], Decimal(row["amount"]))
            if identity in seen:
                raise ValueError(
                    "Duplicate payroll accounting observation; resolve repeated source lines before reconciliation"
                )
            seen.add(identity)
            amount = Decimal(row["amount"])
            grouped[bucket]["positive" if amount > 0 else "negative"] += amount
            grouped[bucket]["count"] += 1
            links.append(
                {
                    "source_role": role,
                    "source_event_id": str(data.source_ids[role]),
                    "source_row_id": row["id"],
                    "registration": key[0],
                    "account": key[1],
                    "currency": key[2],
                    "wage_month": row["wage_month"],
                    "component": row["component"],
                    "category": row["category"],
                    "subject": row["subject"],
                    "posting_date": row["posting_date"],
                    "reference": row["reference"],
                    "amount": row["amount"],
                    "evidence_reference": row["evidence_reference"],
                }
            )
    buckets = sorted(movements["payroll"].keys() | movements["posted"].keys())
    bucket_ids = {bucket: f"payroll-posting:{index}" for index, bucket in enumerate(buckets, 1)}
    for link in links:
        link["comparison_row_id"] = bucket_ids[
            tuple(
                link[field]
                for field in (
                    "registration",
                    "account",
                    "currency",
                    "wage_month",
                    "component",
                    "category",
                    "subject",
                )
            )
        ]
    rows, blocked = [], False
    net: dict[str, defaultdict[tuple[str, str, str], Decimal]] = {
        role: defaultdict(Decimal) for role in ("payroll", "posted")
    }
    for index, bucket in enumerate(buckets, 1):
        expected, posted = (movements[role].get(bucket) for role in ("payroll", "posted"))
        differences = {
            direction: (posted[direction] if posted else Decimal(0))
            - (expected[direction] if expected else Decimal(0))
            for direction in ("positive", "negative")
        }
        state = (
            "UNEXPECTED_GL_PAYROLL_MOVEMENT"
            if expected is None
            else "MISSING_GL_PAYROLL_MOVEMENT"
            if posted is None
            else "DIRECTIONAL_POSTING_VARIANCE"
            if any(abs(value) > data.tolerance for value in differences.values())
            else "MATCHED"
        )
        for role, group in (("payroll", expected), ("posted", posted)):
            if group:
                net[role][bucket[:3]] += group["positive"] + group["negative"]
        rows.append(
            {
                "id": f"payroll-posting:{index}",
                "kind": "posting-comparison",
                "registration": bucket[0],
                "account": bucket[1],
                "currency": bucket[2],
                "wage_month": bucket[3],
                "component": bucket[4],
                "category": bucket[5],
                "subject": bucket[6],
                **{
                    f"{role}_{direction}": str(group[direction]) if group else None
                    for role, group in (("payroll", expected), ("posted", posted))
                    for direction in ("positive", "negative")
                },
                "positive_difference": str(differences["positive"]),
                "negative_difference": str(differences["negative"]),
                "payroll_entry_count": expected["count"] if expected else 0,
                "posted_entry_count": posted["count"] if posted else 0,
                "state": state,
            }
        )
    for index, key in enumerate(sorted(classes), 1):
        opening, closing = (balances[role].get(key) for role in ("opening", "closing"))
        expected_closing = Decimal(opening["amount"]) + net["payroll"][key] if opening else None
        gl_closing = Decimal(opening["amount"]) + net["posted"][key] if opening else None
        difference = (
            Decimal(closing["amount"]) - expected_closing
            if closing and expected_closing is not None
            else None
        )
        gl_difference = (
            Decimal(closing["amount"]) - gl_closing if closing and gl_closing is not None else None
        )
        missing = opening is None or closing is None
        blocked |= missing
        rows.append(
            {
                "id": f"payroll-account:{index}",
                "kind": "account-rollforward",
                "registration": key[0],
                "account": key[1],
                "currency": key[2],
                "account_class": classes[key],
                "normal_sign": "DEBIT_POSITIVE" if classes[key] == "expense" else "CREDIT_POSITIVE",
                "opening_amount": opening["amount"] if opening else None,
                "payroll_movement": str(net["payroll"][key]),
                "posted_movement": str(net["posted"][key]),
                "expected_closing": str(expected_closing) if expected_closing is not None else None,
                "actual_closing": closing["amount"] if closing else None,
                "payroll_closing_difference": str(difference) if difference is not None else None,
                "posted_closing_difference": str(gl_difference)
                if gl_difference is not None
                else None,
                "opening_source_row_id": opening["id"] if opening else None,
                "closing_source_row_id": closing["id"] if closing else None,
                "state": "MISSING_OPENING_OR_CLOSING_GL_CONTROL"
                if missing
                else "GL_BALANCE_ROLLFORWARD_VARIANCE"
                if gl_difference is not None and abs(gl_difference) > data.tolerance
                else "PAYROLL_BALANCE_VARIANCE"
                if difference is not None and abs(difference) > data.tolerance
                else "MATCHED",
            }
        )
    return {
        **result(
            rows,
            blocked=blocked,
            limitations=[
                "Assessed payroll accounting allocations only; expense accounts are debit-positive and liability accounts credit-positive",
                "Accrual, settlement and adjustment categories and wage-month attribution are assessed source inputs, not inferred from the GL",
                "Settlement journal postings do not prove bank execution; use the separate payroll/channel/bank or explicit obligation allocation workflow",
                "Registers, legal wage and tax calculations, pension eligibility, complete balanced journals and statutory filing remain separate procedures",
                "No currency, employer registration, wage month, component, posting category or assessed subject is netted against another partition",
                "Subject identity is an assessed source input; aggregate journals require independently evidenced allocation to comparable subjects before matching",
            ],
        ),
        "payroll_posting_links": links,
        "payroll_ledger_scope": {
            "from": start.isoformat(),
            "through": data.as_of.isoformat(),
            "opening_date": opening_date.isoformat(),
            "normal_sign_basis": "EXPENSE_DEBIT_POSITIVE_LIABILITY_CREDIT_POSITIVE",
        },
        "execution_mode": "rules_baseline",
    }
