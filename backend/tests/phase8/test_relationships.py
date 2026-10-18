from decimal import Decimal

import pytest

from app.modules.tp.relationships import ownership_candidates


def edge(a, b, weight):
    return {
        "id": a + b,
        "from_party_id": a,
        "to_party_id": b,
        "relationship_type": "ownership",
        "ownership": weight,
    }


def test_indirect_common_and_circular_ownership_remain_candidates():
    result = ownership_candidates(
        [edge("A", "B", ".8"), edge("B", "C", ".5"), edge("A", "D", ".9"), edge("C", "A", ".1")]
    )
    indirect = next(x for x in result["ownership_paths"] if x["party_path"] == ["A", "B", "C"])
    assert Decimal(indirect["path_ownership"]) == Decimal(".40")
    assert indirect["relationship_ids"] == ["AB", "BC"]
    assert result["common_ownership_candidates"][0]["common_direct_owners"] == ["A"]
    assert result["cycles_requiring_review"]
    assert not result["automatic_legal_classification"]


def test_path_growth_is_bounded():
    with pytest.raises(ValueError, match="limit"):
        ownership_candidates([edge("A", "B", "1"), edge("B", "C", "1")], max_paths=1)
