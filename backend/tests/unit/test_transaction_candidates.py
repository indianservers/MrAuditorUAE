import random
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.modules.intelligence.matching import reconcile_transactions
from tests.unit.test_intelligence_algorithms import row
from tests.unit.transaction_matching_baseline import reconcile_transactions as baseline


def test_ambiguity_retains_all_candidates_beyond_fifty():
    result = reconcile_transactions([row("L1", "10")], [row(f"R{i:03}", "10") for i in range(121)])
    assert not result["matches"]
    assert len(result["ambiguous"][0]["candidate_ids"]) == 121
    assert result["ambiguous"][0]["candidate_ids"][-1] == "R120"


def test_original_decimal_totals_are_not_rounded_to_the_process_default_context():
    value = "99999999999999999999.12345678"
    result = reconcile_transactions([row("L1", value), row("L2", value)], [])
    assert result["source_totals"]["AED"] == "199999999999999999998.24691356"
    assert Decimal(result["source_totals"]["AED"]) > Decimal(value)


@pytest.mark.parametrize("seed", range(300))
def test_index_preserves_frozen_matching_decisions_and_source_conservation(seed):
    generator = random.Random(seed)

    def population(prefix):
        return [
            dict(
                row(
                    prefix + str(i),
                    generator.choice(["-2", "-1", "0", "0.01", "1", "1.01", "2", "3"]),
                    reference=generator.choice(["", "R1", "R-1", "R2", "سند١", "ß", "ss"]),
                    party=generator.choice(
                        ["", "-", "Supplier A", "SupplierA", "Other", "شركة ألف", "شركة باء"]
                    ),
                    currency=generator.choice(["AED", "INR"]),
                ),
                date=str(date(2026, 6, 15) + timedelta(days=generator.randrange(5))),
            )
            for i in range(generator.randrange(12))
        ]

    left, right = population("L"), population("R")
    args = (
        generator.choice([Decimal(0), Decimal("0.01"), Decimal(1)]),
        generator.randrange(4),
        generator.randrange(1, 4),
    )
    old, new = baseline(left, right, *args), reconcile_transactions(left, right, *args)

    def individual(result):
        return [match for match in result["matches"] if match["rule"] != "BOUNDED_REFERENCE_GROUP"]

    assert individual(new) == individual(old), seed
    assert all(match in old["matches"] for match in new["matches"]), seed
    assert new["source_totals"] == old["source_totals"]
    assert new["destination_totals"] == old["destination_totals"]
    for population, side in ((left, "left"), (right, "right")):
        used = [identifier for match in new["matches"] for identifier in match[side + "_ids"]]
        assert len(used) == len(set(used)) == new["matched_" + side + "_count"]
        assert new["unmatched_" + side] == [
            item for item in population if item["id"] not in set(used)
        ]
    assert [r["left_id"] for r in new["ambiguous"]] == [r["left_id"] for r in old["ambiguous"]]
    for before, after in zip(old["ambiguous"], new["ambiguous"]):
        assert before["candidate_ids"] == after["candidate_ids"][:50]


def test_same_amount_unique_references_do_not_require_a_quadratic_search():
    left = [row(f"L{i}", "100", reference=f"REF-{i}") for i in range(20000)]
    right = [row(f"R{i}", "100", reference=f"REF-{i}") for i in range(20000)]
    result = reconcile_transactions(left, right)
    assert len(result["matches"]) == 20000
    assert result["candidate_checks"] == 40000
    assert not result["unmatched_left"] and not result["unmatched_right"]


def test_same_reference_and_amount_different_parties_are_indexed_separately():
    left = [row(f"L{i}", "100", reference="SAME", party=f"Party {i}") for i in range(20000)]
    right = [row(f"R{i}", "100", reference="SAME", party=f"Party {i}") for i in range(20000)]
    result = reconcile_transactions(left, right)
    assert len(result["matches"]) == 20000 and result["candidate_checks"] == 40000


def test_homogeneous_collisions_fail_before_publishing_a_partial_candidate_graph():
    left = [row(f"L{i}", "100") for i in range(1000)]
    right = [row(f"R{i}", "100") for i in range(1000)]
    with pytest.raises(ValueError, match="candidate search bound exceeded"):
        reconcile_transactions(left, right)


def test_search_bound_is_inclusive_and_never_truncates_candidates():
    right = [row(f"R{i}", "100") for i in range(51)]
    with pytest.raises(ValueError, match="candidate search bound exceeded"):
        reconcile_transactions([row("L", "100")], right, max_candidate_checks=50)
    result = reconcile_transactions([row("L", "100")], right, max_candidate_checks=51)
    assert result["candidate_checks"] == 51 and result["ambiguity_link_count"] == 51
    assert result["ambiguous"][0]["candidate_count"] == 51
    assert not result["ambiguous"][0]["candidate_preview_truncated"]


@pytest.mark.parametrize("limit", [True, 1.5, "100", 0, -1, 100001])
def test_candidate_policy_cannot_be_silently_coerced_or_exceed_the_ceiling(limit):
    with pytest.raises(ValueError, match="search bound must be an integer"):
        reconcile_transactions([], [], max_candidate_checks=limit)


def test_decimal_context_is_restored_after_matching():
    from decimal import getcontext

    before = getcontext()
    state = (before.prec, before.rounding, before.flags.copy(), before.traps.copy())
    reconcile_transactions([row("L", "1")], [row("R", "1")])
    assert getcontext() is before
    assert (before.prec, before.rounding, before.flags, before.traps) == state


@pytest.mark.parametrize("amounts", [(["10", "10"], ["10", "10"]), (["10", "20"], ["15", "15"])])
def test_equal_group_totals_cannot_clear_many_to_many_transactions(amounts):
    left = [row(f"L{i}", amount) for i, amount in enumerate(amounts[0])]
    right = [row(f"R{i}", amount) for i, amount in enumerate(amounts[1])]
    assert baseline(left, right)["matches"]
    result = reconcile_transactions(left, right)
    assert not result["matches"]
    assert result["unmatched_left"] == left and result["unmatched_right"] == right


def test_group_fallback_cannot_override_an_individual_ambiguity():
    left = [row("L", "10")]
    right = [row("R1", "10"), row("R2", "10", party="")]
    assert baseline(left, right)["matches"]
    result = reconcile_transactions(left, right)
    assert not result["matches"] and len(result["ambiguous"][0]["candidate_ids"]) == 2


@pytest.mark.parametrize("reverse", [False, True])
def test_uncontested_single_sided_reference_groups_remain_available(reverse):
    left = [row("L", "10")]
    right = [row("R1", "4"), row("R2", "6")]
    if reverse:
        left, right = right, left
    result = reconcile_transactions(left, right)
    assert len(result["matches"]) == 1 and result["matches"][0]["rule"] == "BOUNDED_REFERENCE_GROUP"


@pytest.mark.parametrize(
    "change", ["contract", "count", "duplicates", "truncated", "total", "boolean", "string"]
)
def test_legacy_or_incomplete_candidates_cannot_pass_approval(change):
    from app.modules.country_workflows.review import approval_error
    from app.modules.intelligence.matching_review import saved_candidates_complete

    body = dict(
        workflow="bank-brs",
        matching_contract="indexed-transaction-candidates/1",
        ambiguity_link_count=2,
        rows=[],
        ambiguous=[
            dict(
                left_id="L",
                candidate_ids=["R1", "R2"],
                candidate_count=2,
                candidate_preview_truncated=False,
            )
        ],
    )
    if change == "contract":
        body.pop("matching_contract")
    elif change == "total":
        body["ambiguity_link_count"] = 1
    elif change == "count":
        body["ambiguous"][0]["candidate_count"] = 121
    elif change == "duplicates":
        body["ambiguous"][0]["candidate_ids"] = ["R1", "R1"]
    elif change == "truncated":
        body["ambiguous"][0]["candidate_preview_truncated"] = True
    elif change == "boolean":
        body["ambiguous"][0]["candidate_count"] = True
    else:
        body["ambiguous"][0]["candidate_count"] = "2"
    assert not saved_candidates_complete(body)
    assert "complete retained" in approval_error(body)


def test_complete_or_unambiguous_results_preserve_the_existing_review_contract():
    from app.modules.intelligence.matching_review import saved_candidates_complete

    result = reconcile_transactions(
        [row("L", "1")], [row("R1", "1"), row("R2", "1")], max_group_size=1
    )
    assert saved_candidates_complete(result)
    assert saved_candidates_complete(dict(ambiguous=[]))


async def test_candidate_review_identifies_a_proposal_for_another_book_item():
    from types import SimpleNamespace

    from app.modules.intelligence.matching_review import candidate_page

    left = [row("L0", "1", reference=""), row("L1", "1", reference="B")]
    right = [row("R1", "1", reference="B"), row("R2", "1", reference="C")]
    body = dict(reconcile_transactions(left, right), source_rows=left, destination_rows=right)
    page = await candidate_page(
        None, None, None, SimpleNamespace(kind="reconciliation", body=body), "L0", 0, 25
    )
    assert page["items"][0]["machine_match"]["left_ids"] == ["L1"]
    assert page["items"][1]["machine_match"] is None


def test_workbook_keeps_machine_proposals_when_exception_rows_are_primary():
    import io

    from openpyxl import load_workbook

    from app.modules.intelligence.exports import render

    left = [row("L0", "1", reference=""), row("L1", "1", reference="B")]
    right = [row("R1", "1", reference="B"), row("R2", "1", reference="C")]
    body = dict(
        reconcile_transactions(left, right),
        workflow="bank-brs",
        rows=[{"id": "L0", "issue": "UNRESOLVED"}],
    )
    event = dict(
        id="SYNTHETIC-MIXED",
        dependencies=[],
        kind="country-workflow",
        version=1,
        sha256="a" * 64,
        created_at="2026-06-30T00:00:00Z",
        body=body,
    )
    content, _ = render(event, "xlsx")
    workbook = load_workbook(io.BytesIO(content), read_only=True)
    assert list(workbook["Rows"].values)[1] == ("L0", "UNRESOLVED")
    proposals = list(workbook["Matched proposals"].values)
    assert len(proposals) == 2
    assert "L1" in proposals[1][0] and "R1" in proposals[1][1]
    candidates = list(workbook["Matching candidates"].values)
    assert len(candidates) == 3
    assert candidates[-1][:4] == ("L0", "R2", "2", "COMPLETE_RETAINED_CANDIDATES")
