"""Day-granular permission conflicts within explicitly declared analysis scopes."""

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

MAX_COMPARISONS = 1000000
MAX_SOURCE_PAIRS = 10000


def merged_intervals(values):
    merged: list[tuple[date, date]] = []
    for start, end in sorted(set(values)):
        if merged and (
            start <= merged[-1][1]
            or (merged[-1][1] < date.max and start == merged[-1][1] + timedelta(days=1))
        ):
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def calculate(rule, access):
    start, end = getattr(access, "period_start", None) or access.as_of, access.as_of
    if start > end:
        raise ValueError("SoD analysis start must not follow its assessment date")
    if not access.assignments or len(access.assignments) > 10000:
        raise ValueError(
            "SoD requires 1–10000 supplied assignments; nil scope needs separate assessment"
        )
    if not rule.pairs or len(rule.pairs) > 100:
        raise ValueError("SoD requires 1–100 explicit incompatible permission pairs")
    if getattr(rule, "system", access.system) != access.system:
        raise ValueError("Access and SoD definition systems must match")
    mode = getattr(rule, "scope_mode", "exact")
    overlaps = getattr(rule, "scope_overlaps", [])
    if (
        mode not in {"exact", "reviewed-overlap"}
        or (mode == "exact" and overlaps)
        or (mode == "reviewed-overlap" and not overlaps)
    ):
        raise ValueError("Reviewed scope overlaps require an explicit nonempty overlap policy")
    effective_from, effective_to = (
        getattr(rule, "effective_from", None),
        getattr(rule, "effective_to", None),
    )
    if (
        getattr(access, "period_start", None) is not None or mode == "reviewed-overlap"
    ) and effective_from is None:
        raise ValueError(
            "Period/overlap analysis requires an effective-dated definition covering the whole requested window"
        )
    if (effective_from is not None and effective_from > start) or (
        effective_to is not None and effective_to < end
    ):
        raise ValueError(
            "SoD definition does not cover the entire analysis window; partition policy changes explicitly"
        )
    scope_map = {}
    neighbours = defaultdict(set)
    mappings = []
    for overlap in overlaps:
        pair = frozenset((overlap.first_scope, overlap.second_scope))
        if len(pair) != 2 or pair in scope_map:
            raise ValueError("Scope overlaps must be distinct direct relationships")
        scope_map[pair] = overlap
        neighbours[overlap.first_scope].add(overlap.second_scope)
        neighbours[overlap.second_scope].add(overlap.first_scope)
        mappings.append(
            {
                "first_scope": overlap.first_scope,
                "second_scope": overlap.second_scope,
                "rationale": overlap.rationale,
                "evidence_reference": overlap.evidence_reference,
            }
        )
    grouped: dict[str, Any] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    intersecting = 0
    for index, assignment in enumerate(access.assignments, 1):
        if assignment.valid_to and assignment.valid_to < assignment.valid_from:
            raise ValueError("Access validity end precedes start")
        lo, hi = max(start, assignment.valid_from), min(end, assignment.valid_to or end)
        if lo <= hi:
            grouped[assignment.principal][assignment.permission][assignment.scope].append(
                (index, lo, hi)
            )
            intersecting += 1
    conflicts: list[dict[str, Any]] = []
    source_pairs: list[dict[str, Any]] = []
    intervals: list[dict[str, Any]] = []
    comparisons = 0
    for principal in sorted(grouped):
        permissions = grouped[principal]
        for pair in rule.pairs:
            left, right = permissions.get(pair.first, {}), permissions.get(pair.second, {})
            for first_scope in sorted(left):
                targets = ({first_scope} | neighbours[first_scope]) & set(right)
                for second_scope in sorted(targets):
                    related = (
                        scope_map.get(frozenset((first_scope, second_scope)))
                        if first_scope != second_scope
                        else None
                    )
                    hits: list[dict[str, Any]] = []
                    windows = []
                    for first_index, first_from, first_to in left[first_scope]:
                        for second_index, second_from, second_to in right[second_scope]:
                            comparisons += 1
                            if comparisons > MAX_COMPARISONS:
                                raise ValueError(
                                    "SoD interval comparison bound exceeded; partition the approved scope"
                                )
                            lo, hi = max(first_from, second_from), min(first_to, second_to)
                            if lo > hi:
                                continue
                            if len(source_pairs) + len(hits) >= MAX_SOURCE_PAIRS:
                                raise ValueError(
                                    "SoD retained assignment-pair bound exceeded; partition the approved scope"
                                )
                            hits.append(
                                {
                                    "first_assignment_index": first_index,
                                    "second_assignment_index": second_index,
                                    "conflict_from": lo.isoformat(),
                                    "conflict_through": hi.isoformat(),
                                }
                            )
                            windows.append((lo, hi))
                    if not hits:
                        continue
                    identifier = f"sod-conflict:{len(conflicts) + 1}"
                    base = {
                        "conflict_id": identifier,
                        "principal": principal,
                        "first": pair.first,
                        "second": pair.second,
                        "first_scope": first_scope,
                        "second_scope": second_scope,
                    }
                    union = [
                        {"conflict_from": lo.isoformat(), "conflict_through": hi.isoformat()}
                        for lo, hi in merged_intervals(windows)
                    ]
                    conflicts.append(
                        {
                            **base,
                            "scope": first_scope if first_scope == second_scope else None,
                            "rationale": pair.rationale,
                            "scope_basis": "EXACT_SCOPE"
                            if related is None
                            else "REVIEWED_DIRECT_OVERLAP",
                            "scope_evidence_reference": related.evidence_reference
                            if related
                            else None,
                            "scope_rationale": related.rationale if related else None,
                            "intervals": union,
                            "source_pairs": hits,
                            "compensating_control_verified": False,
                        }
                    )
                    source_pairs.extend({**base, **hit} for hit in hits)
                    intervals.extend({**base, **window} for window in union)
    return {
        "sod_contract": "permission-overlap-intervals/1",
        "system": access.system,
        "as_of": end.isoformat(),
        "analysis_from": start.isoformat(),
        "analysis_through": end.isoformat(),
        "analysis_mode": "point-in-time"
        if getattr(access, "period_start", None) is None
        else "period-intervals",
        "population_basis": getattr(access, "population_basis", "point-in-time-export"),
        "scope_mode": mode,
        "definition_effective_from": effective_from.isoformat() if effective_from else None,
        "definition_effective_to": effective_to.isoformat() if effective_to else None,
        "scope_mappings": mappings,
        "conflicts": conflicts,
        "count": len(conflicts),
        "conflict_intervals": intervals,
        "assignment_pair_links": source_pairs,
        "source_assignments": len(access.assignments),
        "source_principals": len({assignment.principal for assignment in access.assignments}),
        "assignments_intersecting_window": intersecting,
        "interval_comparisons": comparisons,
        "application_roles_inferred": False,
        "scope_relations_inferred": False,
        "source_binding_status": "NOT_VERIFIED_BY_PURE_CALCULATOR",
        "population_completeness": "DECLARED_SCOPE_ONLY_NOT_INDEPENDENTLY_ESTABLISHED",
        "limitations": [
            "Only supplied permission identifiers are compared; application roles, wildcards, identities and cross-system equivalences are not inferred",
            "Validity is day-granular and inclusive; timestamps and source-specific timezone/revocation conventions need separate qualification",
            "Only identical scopes and directly approved overlap mappings are tested; no transitive hierarchy or global-scope meaning is inferred",
            "Permission combinations are review candidates, not performed transactions, verified compensating controls, control deficiencies or SOX/IFC conclusions",
            "A current-only export cannot establish historical access completeness; source scope and coverage require independent assessment",
        ],
    }
