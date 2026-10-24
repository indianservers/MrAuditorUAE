"""Shared Decimal kernels for specialist IFRS and approved business schedules."""

from collections.abc import Callable, Sequence
from decimal import Decimal

ZERO = Decimal(0)
ONE = Decimal(1)


def relative_allocations(
    price: Decimal,
    prices: Sequence[Decimal],
    round_amount: Callable[[Decimal], Decimal],
    *,
    round_total: bool = False,
) -> list[Decimal]:
    if not prices or any(p <= ZERO for p in prices):
        raise ValueError("Positive standalone prices required")
    if price < ZERO:
        raise ValueError("Negative contract price is unsupported")
    from decimal import ROUND_FLOOR

    total = sum(prices, ZERO)
    target = round_amount(price) if round_total else price
    exponent = round_amount(ZERO).as_tuple().exponent
    if not isinstance(exponent, int):
        raise ValueError("Finite monetary rounding required")
    quantum = ONE.scaleb(exponent)
    raw = [price * p / total for p in prices]
    out = [(v / quantum).to_integral_value(rounding=ROUND_FLOOR) * quantum for v in raw]
    remainder = target - sum(out, ZERO)
    order = sorted(range(len(prices)), key=lambda i: (raw[i] - out[i], i), reverse=True)
    units = int(remainder // quantum)
    for i in order[:units]:
        out[i] += quantum
    residue = target - sum(out, ZERO)
    if residue:
        out[order[units % len(prices)]] += residue
    return out


def solve_monotonic_rate(
    npv: Callable[[Decimal], Decimal],
    lower: Decimal,
    upper: Decimal,
    iterations: int,
    tolerance: Decimal | None = None,
) -> tuple[Decimal, Decimal]:
    if lower < ZERO or upper <= lower or npv(lower) < ZERO or npv(upper) > ZERO:
        raise ValueError("No nonnegative effective-rate root within approved bracket")
    for _ in range(iterations):
        mid = (lower + upper) / 2
        value = npv(mid)
        if tolerance is not None and abs(value) <= tolerance:
            return mid, value
        if value > ZERO:
            lower = mid
        else:
            upper = mid
    if tolerance is not None:
        raise ValueError("Effective-rate solver did not converge")
    rate = (lower + upper) / 2
    return rate, npv(rate)


def periodic_present_value(flows, rate):
    return sum((flow["amount"] / (ONE + rate) ** flow["period"] for flow in flows), ZERO)
