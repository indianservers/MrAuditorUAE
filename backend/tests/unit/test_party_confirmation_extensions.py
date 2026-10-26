"""Blank positive scopes and explicit partial reply coverage; no amount-based allocation."""

import uuid
from copy import deepcopy

import pytest

from app.modules.country_workflows.party_confirmations import PartyConfirmation
from app.modules.country_workflows.review import approval_error
from tests.unit.test_party_confirmations import followup, population, run, source


def coverage(letter="SYN-LETTER-1", item="SYN-INV-1", **changes):
    return {
        "id": "SYN-COVERAGE-1",
        "confirmation_id": letter,
        "item_id": item,
        "as_of": "2026-06-30",
        "evidence_reference": "SYN-RESPONSE-LINE-1",
        **changes,
    }


def partial(currency="AED", followed=False):
    rows = population(currency)
    rows["responses"][0].update(status="partially-received", response_amount="100")
    rows["coverage"] = [coverage()]
    if followed:
        rows["responses"][0] = followup(rows["responses"][0], "partial-response-procedures")
    return rows


@pytest.mark.parametrize("country,currency", [("AE", "AED"), ("IN", "INR")])
@pytest.mark.parametrize("side", ["receivable", "payable"])
def test_blank_request_keeps_assessed_scope_separate_from_the_written_request(
    country, currency, side
):
    rows = population(currency)
    for entries in rows.values():
        for row in entries:
            row["side"] = side
    rows["responses"][0].update(
        request_basis="blank-positive", scope_balance="150", requested_amount=None
    )
    original = deepcopy(rows)
    result = run(rows, country)
    assert rows == original and result["exception_count"] == 0 and not result["blocked"]
    party = result["rows"][-1]
    assert (
        party["scope_balance"] == party["book_balance"] == "150"
        and party["requested_amount"] is None
    )
    assert party["response_amount"] == "150" and party["difference"] == "0"
    assert result["confirmation_contract"] == "positive-party-balance-confirmations/2"


@pytest.mark.parametrize(
    "change", [{"scope_balance": None}, {"requested_amount": "0"}, {"requested_amount": "150"}]
)
def test_blank_request_does_not_infer_scope_or_print_a_requested_zero(change):
    letter = {
        **population()["responses"][0],
        "request_basis": "blank-positive",
        "scope_balance": "150",
        "requested_amount": None,
        **change,
    }
    with pytest.raises(ValueError, match="explicit assessed scope balance"):
        PartyConfirmation.model_validate(letter)


def test_blank_zero_scope_is_not_a_stated_zero_request():
    rows = population()
    rows["items"][2]["amount"] = "-160"
    rows["controls"][0]["amount"] = "0"
    rows["responses"][0].update(
        request_basis="blank-positive",
        scope_balance="0",
        requested_amount=None,
        response_amount="0",
    )
    result = run(rows)
    assert not result["blocked"] and result["rows"][-1]["difference"] == "0"
    assert result["rows"][-1]["requested_amount"] is None


def test_mixed_stated_and_blank_requests_have_three_distinct_money_controls():
    rows = population()
    rows["items"].extend(
        [{**item, "id": item["id"] + "-P2", "counterparty": "PARTY-2"} for item in rows["items"]]
    )
    rows["controls"][0]["amount"] = "300"
    rows["responses"].append(
        {
            **rows["responses"][0],
            "id": "SYN-LETTER-2",
            "counterparty": "PARTY-2",
            "request_basis": "blank-positive",
            "scope_balance": "150",
            "requested_amount": None,
        }
    )
    result = run(rows)
    assert result["exception_count"] == 0
    with pytest.raises(ValueError, match="written-request currency totals do not agree"):
        source("party-confirmations", rows["responses"], confirmation_request_totals={"AED": "300"})
    with pytest.raises(ValueError, match="Source currency control totals do not agree"):
        source("party-confirmations", rows["responses"], control_totals={"AED": "150"})
    with pytest.raises(ValueError, match="written-response currency totals do not agree"):
        source(
            "party-confirmations", rows["responses"], confirmation_response_totals={"AED": "150"}
        )


@pytest.mark.parametrize("country,currency", [("AE", "AED"), ("IN", "INR")])
def test_partial_response_only_compares_explicitly_covered_items(country, currency):
    rows = partial(currency)
    result = run(rows, country, tolerance="1000")
    party = result["rows"][-1]
    assert result["blocked"] and party["state"] == "PARTIAL_RESPONSE_FOLLOWUP_MISSING"
    assert party["book_balance"] == "150" and party["difference"] is None
    assert (
        party["covered_book_balance"] == "100"
        and party["uncovered_book_balance"] == "50"
        and party["covered_response_difference"] == "0"
    )
    assert party["covered_item_source_ids"] == ["SYN-INV-1"]
    assert party["uncovered_item_source_ids"] == ["SYN-INV-2", "SYN-CREDIT-1"]
    assert party["response_comparison_basis"] == "COVERED_ITEMS_ONLY"
    party["auditor_status"] = "EXCEPTION_DOCUMENTED"
    assert approval_error(result)
    rows["responses"][0] = followup(rows["responses"][0], "partial-response-procedures")
    result = run(rows, country)
    assert (
        not result["blocked"] and result["rows"][-1]["state"] == "PARTIAL_RESPONSE_REQUIRES_REVIEW"
    )
    assert approval_error(result)
    result["rows"][-1]["auditor_status"] = "EXCEPTION_DOCUMENTED"
    assert approval_error(result) is None


def test_equal_full_balance_and_zero_net_uncovered_items_still_need_partial_followup():
    rows = partial(followed=True)
    rows["items"][2]["amount"] = "-60"
    rows["controls"][0]["amount"] = "100"
    rows["responses"][0]["requested_amount"] = "100"
    result = run(rows, tolerance="1000")
    party = result["rows"][-1]
    assert not result["blocked"] and party["state"] == "PARTIAL_RESPONSE_REQUIRES_REVIEW"
    assert party["uncovered_book_balance"] == "0" and len(party["uncovered_item_source_ids"]) == 2
    assert (
        party["partial_response_issues"] == ["UNCONFIRMED_ITEMS_REMAIN"]
        and party["difference"] is None
    )


def test_partial_negative_credit_reply_preserves_covered_and_uncovered_signs():
    rows = partial(followed=True)
    rows["responses"][0]["response_amount"] = "-10"
    rows["coverage"][0]["item_id"] = "SYN-CREDIT-1"
    party = run(rows)["rows"][-1]
    assert (
        party["covered_book_balance"] == "-10"
        and party["uncovered_book_balance"] == "160"
        and party["covered_response_difference"] == "0"
    )


@pytest.mark.parametrize("mapped", [False, True])
def test_missing_or_explicitly_empty_item_mapping_never_guesses_coverage(mapped):
    rows = partial(followed=True)
    if mapped:
        rows["coverage"] = []
    else:
        rows.pop("coverage")
    party = run(rows)["rows"][-1]
    assert party["state"] == "PARTIAL_RESPONSE_ITEM_SCOPE_MISSING"
    assert (
        party["covered_book_balance"] is None
        and party["uncovered_book_balance"] is None
        and party["difference"] is None
    )


@pytest.mark.parametrize(
    "change", [{"confirmation_id": "UNKNOWN"}, {"item_id": "UNKNOWN"}, {"as_of": "2026-06-29"}]
)
def test_invalid_coverage_identity_or_date_fails_closed(change):
    rows = partial(followed=True)
    rows["coverage"][0].update(change)
    with pytest.raises(ValueError, match="Partial-response coverage"):
        run(rows)


def test_coverage_cannot_cross_party_or_silently_deduplicate_item_links():
    rows = partial(followed=True)
    rows["coverage"].append({**rows["coverage"][0], "id": "DUP"})
    with pytest.raises(ValueError, match="Duplicate partial-response"):
        run(rows)
    rows = partial(followed=True)
    rows["items"].append({**rows["items"][0], "id": "OTHER-PARTY-ITEM", "counterparty": "OTHER"})
    rows["controls"][0]["amount"] = "250"
    rows["coverage"][0]["item_id"] = "OTHER-PARTY-ITEM"
    with pytest.raises(ValueError, match="own scoped open item"):
        run(rows)


def test_full_scope_is_not_a_partial_reply_and_full_replies_cannot_take_item_mapping():
    rows = partial(followed=True)
    rows["coverage"] = [
        coverage(item=item["id"], id=f"COV-{index}") for index, item in enumerate(rows["items"])
    ]
    assert run(rows)["rows"][-1]["state"] == "PARTIAL_RESPONSE_SCOPE_IS_FULL_POPULATION"
    rows["responses"][0] = population()["responses"][0]
    with pytest.raises(ValueError, match="current partial assessment"):
        run(rows)


def test_partial_reply_requires_specific_followup_and_preserves_covered_differences():
    rows = partial(followed=True)
    rows["responses"][0]["response_amount"] = "90"
    party = run(rows)["rows"][-1]
    assert party["covered_response_difference"] == "-10" and party["difference"] is None
    assert "COVERED_RESPONSE_DIFFERENCE" in party["partial_response_issues"]
    with pytest.raises(ValueError, match="Follow-up kind"):
        PartyConfirmation.model_validate(followup(rows["responses"][0], "alternative-procedures"))


def test_optional_roles_do_not_relax_other_workflow_source_contracts():
    from app.modules.country_workflows.calculations import calculate
    from app.modules.country_workflows.schemas import WorkflowInput

    data = WorkflowInput(
        workflow="subledger-control",
        source_ids={"items": uuid.uuid4(), "controls": uuid.uuid4(), "coverage": uuid.uuid4()},
        as_of="2026-06-30",
        title="SYN invalid optional role",
        rationale="A party-specific optional role cannot expand other workflow contracts",
    )
    with pytest.raises(ValueError, match="every required source role"):
        calculate(data, "AE", {"items": {}, "controls": {}, "coverage": {}})


def test_maximum_open_item_population_keeps_partial_item_membership_exact():
    rows = partial(followed=True)
    rows["items"] = [{**rows["items"][0], "id": f"ITEM-{index:04d}"} for index in range(5000)]
    rows["controls"][0]["amount"] = "500000"
    rows["responses"][0].update(requested_amount="500000", response_amount="499900")
    rows["coverage"] = [
        coverage(item=item["id"], id=f"COV-{index:04d}")
        for index, item in enumerate(rows["items"][:-1])
    ]
    result = run(rows)
    assert not result["blocked"] and result["rows"][-1]["uncovered_item_source_ids"] == [
        "ITEM-4999"
    ]
    assert (
        len(result["confirmation_coverage_links"]) == 4999
        and result["rows"][-1]["covered_book_balance"] == "499900"
    )


def test_partial_export_retains_membership_and_every_reviewed_link():
    from tests.unit.test_xlsx_values import event, workbook

    result = run(partial(followed=True))
    book = workbook(event(**result))
    links = list(book["Confirmation item links"].values)
    assert links[0][-2:] == ("reply_scope_membership", "open_item_source_id")
    assert links[1][-2:] == ("DECLARED_REPLY_COVERED", "SYN-INV-1")
    assert links[2][-2:] == ("NOT_REPLY_COVERED", "SYN-INV-2")
    coverage_rows = list(book["Confirmation coverage links"].values)
    assert len(coverage_rows) == 2
    assert coverage_rows[1][2] == "SYN-INV-1"
    assert coverage_rows[1][-1] == "SYN-RESPONSE-LINE-1"
    book.close()


@pytest.mark.parametrize("country,currency", [("AE", "AED"), ("IN", "INR")])
@pytest.mark.parametrize("case", ["blank-request", "partial-reply"])
def test_saved_blank_and_partial_examples_parse_with_published_document_hashes(
    country, currency, case
):
    import hashlib
    import json
    from pathlib import Path

    from app.modules.country_workflows.calculations import calculate
    from app.modules.country_workflows.schemas import SourceInput, WorkflowInput
    from app.modules.country_workflows.sources import parse_csv

    folder = (
        Path(__file__).resolve().parents[3]
        / "docs/country-workflows/sample-inputs/SYNTHETIC-party-confirmations"
        / country
        / case
    )
    manifest = json.loads((folder / "scope-controls.json").read_text(encoding="utf-8"))
    defaults = {}
    for prefix, document in manifest["supporting_documents"].items():
        assert (
            hashlib.sha256((folder / document["filename"]).read_bytes()).hexdigest()
            == document["sha256"]
        )
        defaults[prefix + "_evidence_version_id"] = str(uuid.uuid4())
        defaults[prefix + "_source_sha256"] = document["sha256"]
    tables = [
        ("items", "audit-open-items", "items.csv"),
        ("controls", "balance-controls", "gl-controls.csv"),
        ("responses", "party-confirmations", "party-assessments.csv"),
    ]
    if case == "partial-reply":
        tables.append(("coverage", "confirmation-item-coverage", "coverage.csv"))
    sources = {}
    for role, kind, filename in tables:
        options = dict(
            evidence_version_id=uuid.uuid4(),
            table_type=kind,
            label="SYN saved example",
            expected_rows=manifest["source_rows"][role],
            control_totals={} if role == "coverage" else manifest["money_controls_each_source"],
        )
        if role == "responses":
            options.update(
                confirmation_request_totals=manifest["confirmation_request_totals"],
                confirmation_response_totals=manifest["confirmation_response_totals"],
            )
        sources[role] = parse_csv(
            (folder / filename).read_bytes(),
            SourceInput.model_validate(options),
            defaults if role == "responses" else None,
        )
    data = WorkflowInput(
        workflow="party-balance-confirmations",
        source_ids={role: uuid.uuid4() for role in sources},
        as_of=manifest["as_of"],
        review_through=manifest["review_through"],
        title="SYN saved confirmation",
        rationale="Independent synthetic example control and expected state",
    )
    result = calculate(data, country, sources)
    assert not result["blocked"]
    assert result["rows"][-1]["state"] == manifest["expected_result"]["party_state"]
    assert result["rows"][-1]["requested_amount"] is None
