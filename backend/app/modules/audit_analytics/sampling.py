"""Reproducible selection; sample size is a professional input, never assurance claimed."""

import random
from collections.abc import Iterable
from decimal import Decimal


def select_items(
    population: Iterable[dict], method: str, size: int, seed: int, threshold: Decimal = Decimal(0)
) -> dict:
    if size < 1:
        raise ValueError("Sample size must be positive")
    rng = random.Random(seed)
    # Reservoir random selection bounds memory by requested sample size.
    selected: list[str] = []
    count = 0
    excluded_zero = excluded_negative = 0
    if method == "random":
        for count, item in enumerate(population, 1):
            if len(selected) < size:
                selected.append(item["id"])
            else:
                index = rng.randrange(count)
                if index < size:
                    selected[index] = item["id"]
        return {
            "selected": [{"id": identifier, "hits": 1} for identifier in selected],
            "population": count,
            "seed": seed,
        }
    items = list(population)
    count = len(items)
    if method == "full":
        selected = [i["id"] for i in items]
    elif method == "high_value":
        selected = [i["id"] for i in items if abs(Decimal(str(i["amount"]))) >= threshold]
    elif method == "risk":
        selected = [
            i["id"]
            for i in sorted(items, key=lambda x: (-Decimal(str(x.get("risk", 0))), str(x["id"])))[
                :size
            ]
        ]
    elif method == "systematic":
        n = min(size, count)
        if n:
            # Fractional interval, single random start; no duplicate indices when n<=N.
            start = Decimal(rng.randrange(10**12)) / Decimal(10**12)
            interval = Decimal(count) / n
            selected = [items[int((start + k) * interval)]["id"] for k in range(n)]
    elif method == "mus":
        positive = []
        for item in items:
            amount = Decimal(str(item["amount"]))
            if amount < 0:
                excluded_negative += 1
            elif amount == 0:
                excluded_zero += 1
            else:
                positive.append((item["id"], amount))
        total = sum((a for _, a in positive), Decimal(0))
        if total <= 0:
            raise ValueError("MUS requires a positive monetary population")
        # Integer lattice in eight decimal currency units gives exact systematic PPS points.
        weights = []
        for identifier, positive_amount in positive:
            scaled = positive_amount * 10**8
            if scaled != scaled.to_integral_value():
                raise ValueError("MUS exceeds supported monetary precision")
            weights.append((identifier, int(scaled)))
        total_units = sum(units for _, units in weights)
        mus_start = rng.randrange(total_units)
        cumulative = 0
        index = 0
        for k in range(size):
            numerator = mus_start + k * total_units
            while (cumulative + weights[index][1]) * size <= numerator:
                cumulative += weights[index][1]
                index += 1
            selected.append(weights[index][0])
    else:
        raise ValueError("Unknown sampling method")
    hits: dict[str, int] = {}
    for identifier in selected:
        hits[identifier] = hits.get(identifier, 0) + 1
    return {
        "selected": [{"id": i, "hits": h} for i, h in hits.items()],
        "population": count,
        "seed": seed,
        "excluded_zero": excluded_zero,
        "excluded_negative": excluded_negative,
        "assurance": "No statistical assurance inferred from sample size",
    }
