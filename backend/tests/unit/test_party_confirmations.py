"""Positive balance letters over many invoices; independently authored control failures."""

import csv
import io
import uuid
from copy import deepcopy
from decimal import Decimal

import pytest

from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.party_confirmations import PartyConfirmation
from app.modules.country_workflows.review import approval_error
from app.modules.country_workflows.schemas import ROW_TYPES, SourceInput, WorkflowInput


def population(currency="AED"):
    items = [
        {
            "id": "SYN-INV-1",
            "account": "AR",
            "counterparty": "PARTY-1",
            "reference": "SYN-INV-1",
            "side": "receivable",
            "currency": currency,
            "document_date": "2026-05-01",
            "due_date": "2026-05-31",
            "balance_date": "2026-06-30",
            "amount": "100",
            "document_type": "invoice",
        }
    ]
    items.extend(
        [
            {**items[0], "id": "SYN-INV-2", "reference": "SYN-INV-2", "amount": "60"},
            {
                **items[0],
                "id": "SYN-CREDIT-1",
                "reference": "SYN-CREDIT-1",
                "document_type": "credit-note",
                "amount": "-10",
            },
        ]
    )
    letter = {
        "id": "SYN-LETTER-1",
        "account": "AR",
        "counterparty": "PARTY-1",
        "side": "receivable",
        "currency": currency,
        "as_of": "2026-06-30",
        "requested_amount": "150",
        "response_amount": "150",
        "status": "received",
        "requested_on": "2026-07-01",
        "responded_on": "2026-07-05",
        "contact_verified": True,
        "independently_received": True,
        "request_reference": "SYN-REQUEST-PAGE-1",
        "response_reference": "SYN-RESPONSE-PAGE-2",
        "request_evidence_version_id": str(uuid.uuid4()),
        "request_source_sha256": "a" * 64,
        "response_evidence_version_id": str(uuid.uuid4()),
        "response_source_sha256": "b" * 64,
        "scope_assessment": "Fictional positive balance scope, sender contact and direct written receipt independently assessed",
    }
    return {
        "items": items,
        "controls": [
            {
                "id": "SYN-GL-1",
                "account": "AR",
                "side": "receivable",
                "currency": currency,
                "as_of": "2026-06-30",
                "amount": "150",
            }
        ],
        "responses": [letter],
    }


def followup(letter, kind="alternative-procedures"):
    return {
        **letter,
        "followup_evidence_version_id": str(uuid.uuid4()),
        "followup_source_sha256": "c" * 64,
        "followup_kind": kind,
        "followup_on": "2026-07-10",
        "followup_reference": "SYN-FOLLOWUP-PAGES-1-3",
        "followup_assessment": "Fictional independently assessed follow-up procedures; no automatic audit conclusion",
    }


def nonresponse(letter, status="pending"):
    values = {
        **letter,
        "status": status,
        "response_amount": None,
        "responded_on": None,
        "response_evidence_version_id": None,
        "response_source_sha256": None,
        "response_reference": "",
        "independently_received": False,
    }
    if status == "not-sent":
        values.update(
            requested_on=None,
            request_evidence_version_id=None,
            request_source_sha256=None,
            request_reference="",
        )
    return values


def source(kind, rows, **changes):
    options = {
        "evidence_version_id": uuid.uuid4(),
        "table_type": kind,
        "label": "SYNTHETIC party balance " + kind,
        "expected_rows": len(rows),
        "control_totals": {},
    }
    totals, requests, responses = {}, {}, {}
    for row in rows:
        amount = (
            (
                row.get("scope_balance")
                if row.get("scope_balance") is not None
                else row.get("requested_amount")
            )
            if kind == "party-confirmations"
            else row.get("amount")
        )
        if amount is not None:
            totals[row["currency"]] = totals.get(row["currency"], Decimal(0)) + Decimal(amount)
        if row.get("requested_amount") is not None:
            requests[row["currency"]] = requests.get(row["currency"], Decimal(0)) + Decimal(
                row["requested_amount"]
            )
        if row.get("response_amount") is not None:
            responses[row["currency"]] = responses.get(row["currency"], Decimal(0)) + Decimal(
                row["response_amount"]
            )
    options["control_totals"] = totals
    if kind == "party-confirmations":
        options["confirmation_request_totals"] = requests
        options["confirmation_response_totals"] = responses
    if not rows:
        options["nil_reason"] = (
            "Fictional independently assessed nil uploaded response population, not confirmed party balances"
        )
    options.update(changes)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(ROW_TYPES[kind].model_fields))
    writer.writeheader()
    writer.writerows(rows)
    from app.modules.country_workflows.sources import parse_csv

    return parse_csv(buffer.getvalue().encode(), SourceInput.model_validate(options))


def run(rows=None, country="AE", sources=None, **changes):
    rows = population() if rows is None else rows
    sources = sources or {
        role: source(kind, rows[role])
        for role, kind in (
            ("items", "audit-open-items"),
            ("controls", "balance-controls"),
            ("responses", "party-confirmations"),
            ("coverage", "confirmation-item-coverage"),
        )
        if role in rows
    }
    data = WorkflowInput.model_validate(
        {
            "workflow": "party-balance-confirmations",
            "source_ids": {role: uuid.uuid4() for role in sources},
            "as_of": "2026-06-30",
            "review_through": "2026-07-15",
            "title": "SYNTHETIC positive party confirmation",
            "rationale": "Explicit positive balance evidence and independent GL/open-item populations",
            **changes,
        }
    )
    return calculate(data, country, sources)


@pytest.mark.parametrize("country,currency", [("AE", "AED"), ("IN", "INR")])
@pytest.mark.parametrize("side", ["receivable", "payable"])
def test_one_written_balance_covers_multiple_invoices_and_a_credit_note(country, currency, side):
    rows = population(currency)
    if side == "payable":
        for records in rows.values():
            for row in records:
                row.update(account="AP", side="payable")
    original = deepcopy(rows)
    result = run(rows, country)
    assert rows == original and not result["blocked"] and result["exception_count"] == 0
    party = result["rows"][-1]
    assert party["open_item_count"] == 3 and party["open_item_source_ids"] == [
        "SYN-INV-1",
        "SYN-INV-2",
        "SYN-CREDIT-1",
    ]
    assert party["book_balance"] == party["requested_amount"] == party["response_amount"] == "150"
    assert party["confirmation_evidence"]["response_source_sha256"] == "b" * 64
    assert result["statutory_calculation_qualified"] is False


@pytest.mark.parametrize("status", ["pending", "not-sent", "undeliverable"])
def test_nonresponses_need_retained_alternatives_and_do_not_become_confirmed(status):
    rows = population()
    rows["responses"][0] = nonresponse(rows["responses"][0], status)
    result = run(rows)
    assert result["blocked"] and result["rows"][-1]["state"] == "ALTERNATIVE_PROCEDURES_MISSING"
    result["rows"][-1]["auditor_status"] = "EXCEPTION_DOCUMENTED"
    assert approval_error(result)
    rows["responses"][0] = followup(rows["responses"][0])
    result = run(rows)
    assert (
        not result["blocked"]
        and result["rows"][-1]["state"] == "ALTERNATIVE_PROCEDURES_REQUIRE_REVIEW"
    )
    assert (
        result["rows"][-1]["confirmation_status"] == status
        and result["rows"][-1]["response_amount"] is None
    )
    assert approval_error(result)
    result["rows"][-1]["auditor_status"] = "EXCEPTION_DOCUMENTED"
    assert approval_error(result) is None


def test_unreliable_written_response_is_preserved_and_not_cleared_by_equal_amounts():
    rows = population()
    rows["responses"][0].update(
        status="unreliable", contact_verified=False, independently_received=False
    )
    assert run(rows)["blocked"]
    rows["responses"][0] = followup(rows["responses"][0])
    result = run(rows)
    assert (
        not result["blocked"]
        and result["rows"][-1]["state"] == "ALTERNATIVE_PROCEDURES_REQUIRE_REVIEW"
    )
    assert (
        result["rows"][-1]["response_amount"] == "150"
        and result["rows"][-1]["confirmation_status"] == "unreliable"
    )


@pytest.mark.parametrize(
    "field,value",
    [("account", "OTHER"), ("counterparty", "OTHER"), ("side", "payable"), ("currency", "INR")],
)
def test_letters_cannot_cross_account_party_side_or_currency(field, value):
    rows = population()
    rows["responses"][0][field] = value
    result = run(rows)
    assert result["blocked"] and len(result["rows"]) == 3
    assert {row["state"] for row in result["rows"][1:]} == {
        "UNKNOWN_PARTY_POPULATION",
        "NOT_REQUESTED_REQUIRES_EVIDENCE",
    }
    unknown = next(row for row in result["rows"] if row["state"] == "UNKNOWN_PARTY_POPULATION")
    assert unknown["book_balance"] is None and unknown["difference"] is None
    assert unknown["response_amount"] == "150"


def test_written_response_totals_are_independent_of_requested_amount_totals():
    rows = population()
    with pytest.raises(ValueError, match="written-response currency totals do not agree"):
        source(
            "party-confirmations", rows["responses"], confirmation_response_totals={"AED": "149"}
        )
    sources = {
        role: source(kind, rows[role])
        for role, kind in (
            ("items", "audit-open-items"),
            ("controls", "balance-controls"),
            ("responses", "party-confirmations"),
        )
    }
    sources["responses"].pop("confirmation_response_totals")
    with pytest.raises(ValueError, match="totals are required"):
        run(sources=sources)


def test_offsetting_party_response_errors_do_not_clear_at_gl_or_source_control_total():
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
            "response_amount": "140",
        }
    )
    rows["responses"][0]["response_amount"] = "160"
    result = run(rows)
    assert result["blocked"] and result["rows"][0]["state"] == "MATCHED"
    assert [row["difference"] for row in result["rows"][1:]] == ["10", "-10"]
    assert all(row["state"] == "RESPONSE_EXCEPTION_FOLLOWUP_MISSING" for row in result["rows"][1:])
    rows["responses"] = [
        followup(letter, "exception-investigation") for letter in rows["responses"]
    ]
    result = run(rows)
    assert not result["blocked"] and approval_error(result)


@pytest.mark.parametrize(
    "change",
    [
        {"as_of": "2026-06-29"},
        {"requested_amount": "149.99"},
        {"responded_on": "2026-07-16"},
        {"contact_verified": False},
        {"independently_received": False},
    ],
)
def test_wrong_scope_future_response_or_missing_independence_cannot_be_dispositioned_away(change):
    rows = population()
    rows["responses"][0].update(change)
    result = run(rows, tolerance="1000")
    assert result["blocked"]
    for row in result["rows"]:
        row["auditor_status"] = "EXCEPTION_DOCUMENTED"
    assert approval_error(result)


def test_followup_date_cannot_escape_review_window_or_precede_the_response():
    rows = population()
    rows["responses"][0] = followup(nonresponse(rows["responses"][0]))
    rows["responses"][0]["followup_on"] = "2026-07-16"
    assert run(rows)["rows"][-1]["state"] == "OUTSIDE_REVIEW_WINDOW"
    with pytest.raises(ValueError, match="precede"):
        PartyConfirmation.model_validate(
            {
                **followup(population()["responses"][0], "exception-investigation"),
                "followup_on": "2026-07-04",
            }
        )


def test_duplicate_current_letters_missing_letter_and_wrong_gl_remain_unresolved():
    rows = population()
    rows["responses"].append({**rows["responses"][0], "id": "DUP"})
    with pytest.raises(ValueError, match="one current"):
        run(rows)
    rows["responses"] = []
    assert run(rows)["blocked"]
    rows = population()
    rows["controls"][0]["amount"] = "149"
    assert run(rows)["blocked"]


@pytest.mark.parametrize(
    "change",
    [
        {"confirmation_type": "negative"},
        {"request_reference": " "},
        {"response_reference": " "},
        {"request_evidence_version_id": None},
        {"response_source_sha256": None},
        {"responded_on": "2026-06-30"},
    ],
)
def test_positive_request_and_response_contract_requires_real_binding_fields(change):
    with pytest.raises(ValueError):
        PartyConfirmation.model_validate({**population()["responses"][0], **change})


def test_confirmed_zero_is_distinct_from_missing_response_and_nil_population():
    rows = population()
    rows["items"][1]["amount"] = "0"
    rows["items"][2]["amount"] = "-100"
    rows["controls"][0]["amount"] = "0"
    rows["responses"][0].update(requested_amount="0", response_amount="0")
    result = run(rows)
    assert not result["blocked"] and result["rows"][-1]["response_amount"] == "0"
    with pytest.raises(ValueError, match="does not qualify nil"):
        run({"items": [], "controls": [], "responses": []})


def test_one_positive_letter_retains_all_five_thousand_open_item_ids():
    rows = population()
    rows["items"] = [{**rows["items"][0], "id": f"SYN-INV-{index:04d}"} for index in range(5000)]
    rows["controls"][0]["amount"] = "500000"
    rows["responses"][0].update(requested_amount="500000", response_amount="500000")
    result = run(rows)
    assert (
        not result["blocked"]
        and len(result["rows"][-1]["open_item_source_ids"]) == 5000
        and result["rows"][-1]["book_balance"] == "500000"
    )
    from tests.unit.test_xlsx_values import event, workbook

    book = workbook(event(**result))
    links = list(book["Confirmation item links"].values)
    assert len(links) == 5001 and links[-1][-1] == "SYN-INV-4999"
    documents = list(book["Confirmation documents"].values)
    assert len(documents) == 3 and documents[-1][-1] == "RETAINED_IDENTITY_ONLY"
    book.close()


def test_disputed_equal_amount_still_requires_investigation_and_never_matches_automatically():
    rows = population()
    rows["responses"][0]["status"] = "disputed"
    assert run(rows)["blocked"]
    rows["responses"][0] = followup(rows["responses"][0], "exception-investigation")
    result = run(rows)
    assert not result["blocked"] and result["rows"][-1]["difference"] == "0"
    assert result["rows"][-1]["state"] == "RESPONSE_EXCEPTION_REQUIRES_REVIEW"
    assert approval_error(result)


def test_one_party_with_two_accounts_remains_two_separate_balance_positions():
    rows = population()
    rows["items"].extend(
        [{**item, "id": item["id"] + "-OTHER", "account": "AR-OTHER"} for item in rows["items"]]
    )
    rows["controls"].append({**rows["controls"][0], "id": "GL-OTHER", "account": "AR-OTHER"})
    rows["responses"].append({**rows["responses"][0], "id": "LETTER-OTHER", "account": "AR-OTHER"})
    result = run(rows)
    assert not result["blocked"] and result["exception_count"] == 0
    assert len(result["rows"]) == 4 and result["confirmation_scope"]["party_positions"] == 2


def test_raw_credit_signed_gl_is_not_automatically_flipped_to_force_payable_agreement():
    rows = population()
    for records in rows.values():
        for row in records:
            row.update(account="AP", side="payable")
    rows["controls"][0]["amount"] = "-150"
    result = run(rows)
    assert result["blocked"] and result["rows"][0]["difference"] == "300"


def test_customer_net_credit_balance_preserves_its_signed_confirmation_amount():
    rows = population()
    rows["items"][2]["amount"] = "-200"
    rows["controls"][0]["amount"] = "-40"
    rows["responses"][0].update(requested_amount="-40", response_amount="-40")
    result = run(rows)
    assert not result["blocked"] and result["exception_count"] == 0
    assert result["rows"][-1]["book_balance"] == result["rows"][-1]["response_amount"] == "-40"
