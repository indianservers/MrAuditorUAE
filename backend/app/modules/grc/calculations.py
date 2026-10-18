from calendar import monthrange
from collections import defaultdict
from decimal import Decimal, localcontext


def risk_score(scoring, assessment):
    def score(likelihood, impact):
        if max(likelihood, impact) > scoring.matrix_size:
            raise ValueError("Risk coordinates exceed approved matrix")
        return (
            Decimal(likelihood * impact)
            if scoring.method == "product"
            else scoring.cells[likelihood - 1][impact - 1]
        )

    inherent = score(assessment.inherent_likelihood, assessment.inherent_impact)
    residual = score(assessment.residual_likelihood, assessment.residual_impact)
    return {
        "inherent": inherent,
        "residual": residual,
        "appetite": scoring.appetite,
        "appetite_breach": residual > scoring.appetite,
        "method": scoring.method,
        "matrix_size": scoring.matrix_size,
        "qualitative_not_probability": True,
    }


def plan_score(plan, scoring):
    used: dict[str, Decimal] = defaultdict(Decimal)
    items = []
    with localcontext() as ctx:
        ctx.prec = 40
        for item in plan.items:
            if set(item.criteria) != set(scoring.criteria_weights):
                raise ValueError("Plan criteria must match the approved weighting model")
            if any(v > scoring.criteria_scale for v in item.criteria.values()):
                raise ValueError("Plan rating exceeds approved criteria scale")
            score = sum(
                (item.criteria[k] * w for k, w in scoring.criteria_weights.items()), Decimal(0)
            )
            if not item.deferred:
                used[str(item.auditor_id)] += item.budget_hours
            items.append(
                {
                    "universe_id": str(item.universe_id),
                    "auditor_id": str(item.auditor_id),
                    "priority": score,
                    "budget_hours": item.budget_hours,
                    "actual_hours": item.actual_hours,
                    "deferred": item.deferred,
                }
            )
        capacities = {str(k): v for k, v in plan.capacity_hours.items()}
        capacity = [
            {
                "auditor_id": uid,
                "budgeted": hours,
                "capacity": capacities.get(uid, Decimal(0)),
                "overbooked": hours > capacities.get(uid, Decimal(0)),
            }
            for uid, hours in used.items()
        ]
        return {
            "items": sorted(items, key=lambda x: (-x["priority"], x["universe_id"])),
            "capacity": capacity,
            "overbooked": any(x["overbooked"] for x in capacity),
            "budgeted_hours": sum(used.values(), Decimal(0)),
            "qualitative_not_probability": True,
        }


def sod(rule, access):
    by_principal = defaultdict(set)
    for item in access.assignments:
        if item.valid_from <= access.as_of and (
            item.valid_to is None or item.valid_to >= access.as_of
        ):
            by_principal[(item.principal, item.scope)].add(item.permission)
    conflicts = []
    for (principal, scope), permissions in sorted(by_principal.items()):
        for pair in rule.pairs:
            if pair.first in permissions and pair.second in permissions:
                conflicts.append(
                    {
                        "principal": principal,
                        "scope": scope,
                        "first": pair.first,
                        "second": pair.second,
                        "rationale": pair.rationale,
                        "compensating_control_verified": False,
                    }
                )
    return {
        "system": access.system,
        "as_of": str(access.as_of),
        "conflicts": conflicts,
        "count": len(conflicts),
        "application_roles_inferred": False,
    }


def next_due(current, frequency):
    from datetime import timedelta

    if frequency in {"daily", "weekly"}:
        return current + timedelta(days=1 if frequency == "daily" else 7)
    months = 1 if frequency == "monthly" else 3
    year = current.year + (current.month - 1 + months) // 12
    month = (current.month - 1 + months) % 12 + 1
    return current.replace(year=year, month=month, day=min(current.day, monthrange(year, month)[1]))
