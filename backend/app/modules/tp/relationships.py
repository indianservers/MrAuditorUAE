"""Arithmetic ownership candidates only; control and family tests remain reviewed facts."""

from collections import defaultdict
from decimal import Decimal
from typing import Any


def ownership_candidates(edges, max_paths=10000):
    graph = defaultdict(list)
    parents = defaultdict(set)
    for edge in edges:
        if edge.get("relationship_type") == "ownership" and edge.get("ownership") is not None:
            a, b = edge["from_party_id"], edge["to_party_id"]
            graph[a].append((b, Decimal(str(edge["ownership"])), edge["id"]))
            parents[b].add(a)
    paths: list[dict[str, Any]] = []
    cycles: list[dict[str, Any]] = []
    for root in sorted(graph):
        stack: list[tuple[str, Decimal, list[str], list[str]]] = [(root, Decimal(1), [root], [])]
        while stack:
            node, weight, seen, references = stack.pop()
            for child, share, reference in graph[node]:
                if len(paths) + len(cycles) >= max_paths:
                    raise ValueError(
                        "Ownership path limit reached; narrow the relationship population"
                    )
                if child in seen:
                    cycles.append(
                        {"parties": seen + [child], "relationship_ids": references + [reference]}
                    )
                    continue
                path = {
                    "owner_id": root,
                    "subject_id": child,
                    "path_ownership": str(weight * share),
                    "party_path": seen + [child],
                    "relationship_ids": references + [reference],
                }
                paths.append(path)
                stack.append((child, weight * share, seen + [child], references + [reference]))
    common = []
    subjects = sorted(parents)
    for i, left in enumerate(subjects):
        for right in subjects[i + 1 :]:
            shared = sorted(parents[left] & parents[right])
            if shared:
                common.append(
                    {"left_party_id": left, "right_party_id": right, "common_direct_owners": shared}
                )
    return {
        "ownership_paths": paths,
        "common_ownership_candidates": common,
        "cycles_requiring_review": cycles,
        "automatic_legal_classification": False,
    }
