"""Bounded identity/amount/date indexes; they select candidates, never approve matches."""

from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(slots=True)
class SearchBudget:
    limit: int
    examined: int = 0

    def charge(self):
        if self.examined >= self.limit:
            raise ValueError(
                "Transaction candidate search bound exceeded; narrow independently controlled "
                "account/period scope while keeping competing transactions together"
            )
        self.examined += 1


class Family:
    def __init__(self, entries):
        amounts = defaultdict(list)
        for entry in entries:
            amounts[entry[0]].append(entry)
        self.amounts = sorted(amounts)
        self.buckets = {}
        for amount, bucket in amounts.items():
            ordered = sorted(bucket, key=lambda entry: (entry[1], entry[2]))
            self.buckets[amount] = ([entry[1] for entry in ordered], ordered)

    def scan(self, amount, day, tolerance, date_tolerance, budget):
        for value in self.amounts[
            bisect_left(self.amounts, amount - tolerance) : bisect_right(
                self.amounts, amount + tolerance
            )
        ]:
            days, entries = self.buckets[value]
            for entry in entries[
                bisect_left(days, day - date_tolerance) : bisect_right(days, day + date_tolerance)
            ]:
                budget.charge()
                yield entry


class TransactionCandidates:
    def __init__(self, rows, normalize):
        self.normalize = normalize
        families: defaultdict[tuple, list] = defaultdict(list)
        for position, row in enumerate(rows):
            value = Decimal(row["amount"])
            if not value.is_finite():
                raise ValueError("Transaction amounts must be finite")
            entry = (value, date.fromisoformat(row["date"]).toordinal(), position, row)
            currency = row["currency"]
            reference = normalize(row.get("reference"))
            party = normalize(row.get("counterparty"))
            if reference:
                families[("ref", currency, reference)].append(entry)
                families[("refparty", currency, reference, party)].append(entry)
                if not row.get("counterparty"):
                    families[("refblank", currency, reference)].append(entry)
            if party:
                families[("party", currency, party)].append(entry)
        self.families = {key: Family(entries) for key, entries in families.items()}

    def query(self, row, mode, tolerance, date_tolerance, budget):
        currency = row["currency"]
        reference = self.normalize(row.get("reference"))
        party = self.normalize(row.get("counterparty"))
        keys: list[tuple] = []
        if mode in {"reference", "all"} and reference:
            if not row.get("counterparty"):
                keys.append(("ref", currency, reference))
            else:
                keys.append(("refparty", currency, reference, party))
                if party:
                    keys.append(("refblank", currency, reference))
        if mode in {"party", "all"} and party:
            keys.append(("party", currency, party))
        amount = Decimal(row["amount"])
        day = date.fromisoformat(row["date"]).toordinal()
        found = {}
        for key in keys:
            family = self.families.get(key)
            if family:
                for entry in family.scan(amount, day, tolerance, date_tolerance, budget):
                    found[entry[2]] = entry
        # Preserve the legacy candidate order: amount then original source position.
        return [
            entry[3] for entry in sorted(found.values(), key=lambda entry: (entry[0], entry[2]))
        ]
