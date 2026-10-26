"""Exact supplied economic ownership paths; no registry or legal UBO conclusion."""

from collections import defaultdict
from datetime import date
from decimal import Decimal, localcontext
from fractions import Fraction
from typing import Any

from app.modules.country_workflows.audit_calculations import result

MAX_TRANSITIONS = 10000
MAX_PATH_STEPS = 50000


def decimal_text(value: Fraction) -> str:
    # Canonical fractions have finite base-ten expansions. Preserve all digits,
    # including products deeper than the general calculator's Decimal context.
    with localcontext() as arithmetic:
        arithmetic.prec = max(80, len(str(value.numerator)) + len(str(value.denominator)) + 10)
        return format(Decimal(value.numerator) / Decimal(value.denominator), "f")


def compare(data, tables, country):
    policies = [
        row
        for row in tables["policy"]
        if row["country"] == country
        and date.fromisoformat(row["effective_from"])
        <= data.as_of
        <= date.fromisoformat(row["effective_to"])
    ]
    if len(policies) != 1:
        return {
            **result([{"id": "policy", "state": "OWNERSHIP_POLICY_MISSING_OR_AMBIGUOUS"}], True),
            "ownership_path_contract": "economic-ownership-paths/1",
            "ownership_paths": [],
            "ownership_path_steps": [],
        }
    policy = policies[0]
    threshold = Fraction(Decimal(policy["threshold"]))
    graph = defaultdict(list)
    identities: dict[str, str] = {}
    active = 0
    for edge in tables["ownership"]:
        if date.fromisoformat(edge["effective_from"]) > data.as_of or (
            edge.get("effective_to") and date.fromisoformat(edge["effective_to"]) < data.as_of
        ):
            continue
        if edge["owner"] in identities and identities[edge["owner"]] != edge["owner_kind"]:
            raise ValueError("Conflicting company/person owner identity")
        identities[edge["owner"]] = edge["owner_kind"]
        graph[edge["company"]].append(edge)
        active += 1
    if any(identities.get(company) == "person" for company in graph):
        raise ValueError("A natural-person identity cannot also be an owned company")
    rows: list[dict[str, Any]] = []
    paths: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []
    if any(identities.get(company) == "person" for company in data.subjects):
        raise ValueError("An ownership company subject cannot be a known natural-person identity")
    transitions = 0
    blocked = False
    for company in data.subjects:
        totals: defaultdict[str, Fraction] = defaultdict(Fraction)
        person_paths = defaultdict(list)
        failures = set()
        first_path = len(paths)

        def emit(chain, weight, *, person=None, gap=None, at_company=None, outgoing=None):
            if len(chain) > 20:
                raise ValueError(
                    "Ownership complexity bound exceeded; select a reviewed bounded graph"
                )
            if len(paths) >= MAX_TRANSITIONS or len(steps) + len(chain) > MAX_PATH_STEPS:
                raise ValueError(
                    "Ownership retained-path bound exceeded; partition the explicitly reviewed subject graph"
                )
            identifier = f"ownership-path:{len(paths) + 1}"
            paths.append(
                {
                    "path_id": identifier,
                    "subject_company": company,
                    "person_id": person,
                    "kind": "graph-gap" if gap else "natural-person",
                    "economic_fraction": decimal_text(weight) if person is not None else None,
                    "reach_fraction": decimal_text(weight),
                    "gap_reason": gap,
                    "gap_at_company": at_company,
                    "observed_outgoing_fraction": decimal_text(outgoing)
                    if outgoing is not None
                    else None,
                    "edge_count": len(chain),
                    "edge_source_ids": [edge["id"] for edge in chain],
                    "company_owner_chain": [company, *[edge["owner"] for edge in chain]],
                }
            )
            for index, edge in enumerate(chain, 1):
                steps.append(
                    {
                        "path_id": identifier,
                        "subject_company": company,
                        "step": index,
                        "edge_source_id": edge["id"],
                        **{
                            field: edge.get(field)
                            for field in (
                                "company",
                                "owner",
                                "owner_kind",
                                "fraction",
                                "effective_from",
                                "effective_to",
                                "evidence_reference",
                            )
                        },
                    }
                )
            if person is not None:
                person_paths[person].append(identifier)

        def walk(node, weight, visited, chain):
            nonlocal transitions
            if len(chain) > 20:
                raise ValueError(
                    "Ownership complexity bound exceeded; select a reviewed bounded graph"
                )
            if node in visited:
                reason = "OWNERSHIP_CYCLE_REQUIRES_ASSESSMENT"
                failures.add(reason)
                emit(chain, weight, gap=reason, at_company=node)
                return
            edges = graph.get(node, [])
            if not edges:
                reason = "CORPORATE_OWNER_EVIDENCE_MISSING"
                failures.add(reason)
                emit(chain, weight, gap=reason, at_company=node)
                return
            outgoing = sum((Fraction(Decimal(edge["fraction"])) for edge in edges), Fraction())
            if outgoing != 1:
                reason = "OWNERSHIP_POPULATION_NOT_COMPLETE"
                failures.add(reason)
                emit(chain, weight, gap=reason, at_company=node, outgoing=outgoing)
            owners = set()
            for edge in edges:
                transitions += 1
                if transitions > MAX_TRANSITIONS:
                    raise ValueError(
                        "Ownership complexity bound exceeded; partition the reviewed subject graph"
                    )
                next_chain = [*chain, edge]
                if edge["owner"] in owners:
                    reason = "DUPLICATE_CURRENT_OWNERSHIP_EDGE"
                    failures.add(reason)
                    emit(
                        next_chain,
                        weight * Fraction(Decimal(edge["fraction"])),
                        gap=reason,
                        at_company=node,
                    )
                    continue
                owners.add(edge["owner"])
                share = weight * Fraction(Decimal(edge["fraction"]))
                if edge["owner_kind"] == "person":
                    totals[edge["owner"]] += share
                    emit(next_chain, share, person=edge["owner"])
                else:
                    walk(edge["owner"], share, {*visited, node}, next_chain)

        walk(company, Fraction(1), set(), [])
        complete = not failures
        for path in paths[first_path:]:
            path["source_graph_complete"] = complete
        if failures:
            blocked = True
            rows.append(
                {
                    "id": "company:" + company,
                    "company": company,
                    "exceptions": sorted(failures),
                    "state": "OWNERSHIP_EVIDENCE_GAPS",
                }
            )
        for person, fraction in sorted(totals.items()):
            candidate = (
                fraction > threshold
                if policy["comparison"] == "greater-than"
                else fraction >= threshold
            )
            rows.append(
                {
                    "id": f"ownership-person:{len(rows) + 1}",
                    "company": company,
                    "person_id": person,
                    "economic_fraction": decimal_text(fraction),
                    "fraction_scope": "COMPLETE_SUPPLIED_GRAPH"
                    if complete
                    else "INCOMPLETE_GRAPH_PARTIAL_PATHS",
                    "threshold_candidate": candidate if complete else None,
                    "observed_threshold_reached": candidate,
                    "policy_source_id": policy["id"],
                    "ownership_path_ids": person_paths[person],
                    "path_count": len(person_paths[person]),
                    "state": "OWNERSHIP_EVIDENCE_GAPS"
                    if not complete
                    else "REQUIRES_UBO_REVIEW"
                    if candidate
                    else "MATCHED",
                }
            )
    return {
        **result(
            rows,
            blocked,
            [
                "Economic fractions use exact supplied decimal shares along retained paths; no voting, nominee, trust or control-rights conclusion is inferred",
                "Threshold and operator come from an independently reviewed country/date policy; no legal threshold or registry authentication is supplied by this calculation",
                "Incomplete, cyclic and duplicate graphs block approval; partial observed fractions are not complete ownership or threshold determinations",
                "Agreement describes the supplied graph, not population completeness, legal UBO qualification, onboarding approval or an audit opinion",
            ],
        ),
        "ownership_path_contract": "economic-ownership-paths/1",
        "ownership_paths": paths,
        "ownership_path_steps": steps,
        "ownership_scope": {
            "country": country,
            "as_of": data.as_of.isoformat(),
            "policy_source_id": policy["id"],
            "policy_evidence_reference": policy["evidence_reference"],
            "threshold": policy["threshold"],
            "comparison": policy["comparison"],
            "subject_companies": list(data.subjects),
            "active_edges": active,
            "inactive_edges": len(tables["ownership"]) - active,
            "explored_transitions": transitions,
        },
    }
