"""Explainable Decimal matching. Machine proposals never imply auditor approval."""

import re
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import date
from decimal import Decimal


def normal(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def compare_voucher(transaction, document, amount_tolerance=Decimal(0), date_tolerance=0):
    fields = document["fields"]
    checks = []
    pairs = [
        ("reference", transaction.get("reference"), fields.get("invoice_number")),
        (
            "party",
            transaction.get("counterparty"),
            fields.get("supplier") or fields.get("customer"),
        ),
        ("currency", transaction.get("currency"), fields.get("currency")),
    ]
    for name, left, right in pairs:
        checks.append(
            {
                "field": name,
                "ledger": left,
                "evidence": right,
                "result": "MISSING"
                if not left or not right
                else "MATCH"
                if normal(left) == normal(right)
                else "DIFFERENT",
            }
        )
    amount = fields.get("gross_amount")
    delta = None if amount is None else Decimal(transaction["amount"]) - Decimal(amount)
    checks.append(
        {
            "field": "amount",
            "ledger": transaction["amount"],
            "evidence": amount,
            "variance": None if delta is None else str(delta),
            "result": "MISSING"
            if delta is None
            else "MATCH"
            if abs(delta) <= amount_tolerance
            else "DIFFERENT",
        }
    )
    when = fields.get("document_date")
    days = (
        None
        if not when or not transaction.get("date")
        else (date.fromisoformat(transaction["date"]) - date.fromisoformat(when)).days
    )
    checks.append(
        {
            "field": "date",
            "ledger": transaction.get("date"),
            "evidence": when,
            "variance_days": days,
            "result": "MISSING"
            if days is None
            else "MATCH"
            if abs(days) <= date_tolerance
            else "DIFFERENT",
        }
    )
    for name, key in [
        ("tax_amount", "tax_amount"),
        ("purchase_order", "purchase_order"),
        ("payment_reference", "payment_reference"),
    ]:
        if transaction.get(key) is not None:
            value = fields.get(key)
            match = value is not None and (
                abs(Decimal(transaction[key]) - Decimal(value)) <= amount_tolerance
                if name == "tax_amount"
                else normal(value) == normal(transaction[key])
            )
            checks.append(
                {
                    "field": name,
                    "ledger": transaction[key],
                    "evidence": value,
                    "result": "MISSING" if value is None else "MATCH" if match else "DIFFERENT",
                }
            )
    matched = sum(c["result"] == "MATCH" for c in checks)
    different = any(c["result"] == "DIFFERENT" for c in checks)
    status = (
        "MATCHED"
        if matched == len(checks)
        else "PARTIALLY_MATCHED"
        if matched >= 2
        else "NOT_MATCHED"
    )
    if different and status == "MATCHED":
        status = "PARTIALLY_MATCHED"
    return {
        "machine_status": status,
        "candidate_strength": matched,
        "strength_interpretation": "Count of deterministic field agreements; not a probability",
        "checks": checks,
        "auditor_status": "NOT_REVIEWED",
        "document_review_status": document.get("review_status", "UNVERIFIED"),
    }


def reconcile_transactions(left, right, tolerance=Decimal(0), date_tolerance=0, max_group_size=3):
    if len(left) > 20000 or len(right) > 20000:
        raise ValueError("Transaction matching bound is 20,000 rows per side; partition the source")
    if len({r["id"] for r in left}) != len(left) or len({r["id"] for r in right}) != len(right):
        raise ValueError("Duplicate source row identifiers")
    used_left = set()
    used_right = set()
    matches = []
    ambiguous = []
    index = defaultdict(list)
    left_index = defaultdict(list)
    for row in right:
        index[(row["currency"], Decimal(row["amount"]))].append(row)
    for row in left:
        left_index[(row["currency"], Decimal(row["amount"]))].append(row)
    right_amounts = {
        c: sorted({amount for currency, amount in index if currency == c})
        for c in {r["currency"] for r in right}
    }
    left_amounts = {
        c: sorted({amount for currency, amount in left_index if currency == c})
        for c in {r["currency"] for r in left}
    }

    def amount_candidates(row, lookup, amounts):
        currency, value = row["currency"], Decimal(row["amount"])
        values = amounts.get(currency, [])
        for amount in values[
            bisect_left(values, value - tolerance) : bisect_right(values, value + tolerance)
        ]:
            yield from lookup[(currency, amount)]

    def compatible(a, b):
        return (
            a["currency"] == b["currency"]
            and abs(Decimal(a["amount"]) - Decimal(b["amount"])) <= tolerance
            and abs((date.fromisoformat(a["date"]) - date.fromisoformat(b["date"])).days)
            <= date_tolerance
            and (
                not a.get("counterparty")
                or not b.get("counterparty")
                or normal(a["counterparty"]) == normal(b["counterparty"])
            )
        )

    for row in left:
        # Exact amounts use an index; tolerances use a bounded candidate set.
        candidates = amount_candidates(row, index, right_amounts)
        candidates = [r for r in candidates if r["id"] not in used_right and compatible(row, r)]
        referenced = [
            r
            for r in candidates
            if normal(row.get("reference"))
            and normal(r.get("reference")) == normal(row["reference"])
        ]
        candidates = referenced or candidates
        if len(candidates) > 1:
            ambiguous.append(
                {
                    "left_id": row["id"],
                    "candidate_ids": [r["id"] for r in candidates[:50]],
                    "reason": "Multiple equally supported deterministic candidates",
                }
            )
            continue
        if len(candidates) == 1:
            target = candidates[0]
            competitors = [
                a
                for a in amount_candidates(target, left_index, left_amounts)
                if a["id"] not in used_left
                and compatible(a, target)
                and (
                    not referenced or normal(a.get("reference")) == normal(target.get("reference"))
                )
            ]
            if len(competitors) != 1:
                continue
            used_left.add(row["id"])
            used_right.add(target["id"])
            matches.append(
                {
                    "left_ids": [row["id"]],
                    "right_ids": [target["id"]],
                    "rule": "REFERENCE_AMOUNT_DATE" if referenced else "AMOUNT_DATE_UNIQUE",
                    "variance": str(Decimal(row["amount"]) - Decimal(target["amount"])),
                    "auditor_status": "NOT_REVIEWED",
                }
            )
    left_groups: dict[tuple, list] = defaultdict(list)
    right_groups: dict[tuple, list] = defaultdict(list)
    for rows, groups, used in [(left, left_groups, used_left), (right, right_groups, used_right)]:
        for row in rows:
            if row["id"] not in used and normal(row.get("reference")):
                groups[
                    (row["currency"], normal(row["reference"]), normal(row.get("counterparty")))
                ].append(row)
    for key, source in left_groups.items():
        target = right_groups.get(key, [])
        if not target or len(source) > max_group_size or len(target) > max_group_size:
            continue
        if (
            max(date.fromisoformat(r["date"]) for r in source + target)
            - min(date.fromisoformat(r["date"]) for r in source + target)
        ).days > date_tolerance:
            continue
        delta = sum((Decimal(r["amount"]) for r in source), Decimal(0)) - sum(
            (Decimal(r["amount"]) for r in target), Decimal(0)
        )
        if abs(delta) <= tolerance:
            used_left.update(r["id"] for r in source)
            used_right.update(r["id"] for r in target)
            matches.append(
                {
                    "left_ids": [r["id"] for r in source],
                    "right_ids": [r["id"] for r in target],
                    "rule": "BOUNDED_REFERENCE_GROUP",
                    "variance": str(delta),
                    "auditor_status": "NOT_REVIEWED",
                    "limitation": "Group aggregate agreement does not establish an individual payment allocation",
                }
            )

    def totals(rows):
        return {
            currency: str(
                sum((Decimal(r["amount"]) for r in rows if r["currency"] == currency), Decimal(0))
            )
            for currency in sorted({r["currency"] for r in rows})
        }

    return {
        "matches": matches,
        "ambiguous": ambiguous,
        "unmatched_left": [r for r in left if r["id"] not in used_left],
        "unmatched_right": [r for r in right if r["id"] not in used_right],
        "source_totals": totals(left),
        "destination_totals": totals(right),
        "matched_left_count": len(used_left),
        "matched_right_count": len(used_right),
        "machine_status": "REQUIRES_REVIEW",
        "adjustments_posted": False,
        "group_search_bound": max_group_size,
    }


def age_open_items(rows, as_of, buckets, fallback=False):
    labels = (
        ["Current", f"1–{buckets[0]}"]
        + [f"{a + 1}–{b}" for a, b in zip(buckets, buckets[1:])]
        + [f"Over {buckets[-1]}"]
    )
    currencies: dict[str, list[Decimal]] = {}
    details = []
    warnings = []
    for row in rows:
        when = row.get("due_date")
        if not when and fallback:
            when = row.get("document_date")
            warnings.append(
                {
                    "row_id": row["id"],
                    "assumption": "Document date substituted for unavailable due date",
                }
            )
        if not when:
            raise ValueError(
                "Due date unavailable; explicitly select document-date fallback or correct the source"
            )
        days = (as_of - date.fromisoformat(when)).days
        index = (
            0
            if days <= 0
            else next((i + 1 for i, edge in enumerate(buckets) if days <= edge), len(labels) - 1)
        )
        totals = currencies.setdefault(row["currency"], [Decimal(0) for _ in labels])
        totals[index] += Decimal(row["open_amount"])
        details.append({**row, "days_overdue": days, "bucket": labels[index]})
    return {
        "as_of": as_of.isoformat(),
        "buckets": labels,
        "totals_by_currency": {
            c: {
                "total": str(sum(values, Decimal(0))),
                "buckets": {label: str(value) for label, value in zip(labels, values)},
            }
            for c, values in currencies.items()
        },
        "items": details,
        "assumptions": warnings,
        "basis": "Authoritative uploaded open-item amounts; GL postings are not assumed unpaid",
    }
