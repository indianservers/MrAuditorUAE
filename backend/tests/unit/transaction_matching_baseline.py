"""Frozen pre-index decision oracle from f547bb7; not a production fallback.

Individual matching decisions and source conservation are compared. Historical
candidate truncation and unsafe group fallback are not compatibility requirements.
"""

import unicodedata
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import date
from decimal import Decimal


def normal(value):
    return "".join(
        c for c in unicodedata.normalize("NFKC", str(value or "")).casefold() if c.isalnum()
    )


def reconcile_transactions(left, right, tolerance=Decimal(0), date_tolerance=0, max_group_size=3):
    if (
        not tolerance.is_finite()
        or tolerance < 0
        or not 0 <= date_tolerance <= 365
        or not 1 <= max_group_size <= 6
    ):
        raise ValueError("Invalid bounded matching policy")
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
            and (
                bool(normal(a.get("reference")))
                and normal(a.get("reference")) == normal(b.get("reference"))
                or bool(normal(a.get("counterparty")))
                and normal(a.get("counterparty")) == normal(b.get("counterparty"))
            )
            and Decimal(a["amount"]) != 0
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
                    "rule": "REFERENCE_AMOUNT_DATE" if referenced else "PARTY_AMOUNT_DATE_UNIQUE",
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
        if not (
            all(Decimal(row["amount"]) > 0 for row in source + target)
            or all(Decimal(row["amount"]) < 0 for row in source + target)
        ):
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
