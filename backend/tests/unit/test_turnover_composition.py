"""Multiple reviewed turnover books retain signed rows and reject overlap."""

import uuid
from copy import deepcopy

import pytest

from app.modules.country_workflows.turnover_composition import TurnoverCompositionInput, source_rows
from app.modules.country_workflows.turnover_ledger import CONTRACT as LEDGER
from tests.unit.test_turnover_bridge import populations


def fixture(country="AE", ledger=False):
    ids = [uuid.uuid4(), uuid.uuid4()]
    data = TurnoverCompositionInput(
        source_ids=ids,
        expected_rows=2,
        currency="AED" if country == "AE" else "INR",
        expected_amount="95.00000001",
        label="SYNTHETIC books composition",
        assessment="Disjoint reviewed book schedules and controls",
    )
    base = populations(country)["books"][0]
    bodies = {}
    for index, identifier in enumerate(ids):
        body = dict(
            table_type="turnover-amounts",
            source_identity=f"evidence:{index}",
            rows=[
                dict(
                    base,
                    id=f"row{index}",
                    reference=f"REF{index}",
                    amount="100.00000001" if index == 0 else "-5",
                )
            ],
        )
        if ledger:
            body.update(
                parser_version=LEDGER,
                source_identity="snapshot:shared",
                allowed_source_roles=["books"],
                native_metadata={
                    "account_ids": [str(uuid.uuid4())],
                    "period_start": "2026-04-01",
                    "period_end": "2026-06-30",
                },
            )
        bodies[str(identifier)] = body
    return data, bodies


@pytest.mark.parametrize("country", ["AE", "IN"])
@pytest.mark.parametrize("ledger", [False, True])
def test_disjoint_books_preserve_precision_and_origin(country, ledger):
    data, bodies = fixture(country, ledger)
    rows, totals = source_rows(bodies, data, country)
    assert totals == {data.currency: "95.00000001"}
    assert [row["amount"] for row in rows] == ["100.00000001", "-5"]
    assert len({row["id"] for row in rows}) == 2
    assert rows[1]["source_component_event_id"] == str(data.source_ids[1])
    assert rows[1]["source_component_row_id"] == "row1"


@pytest.mark.parametrize(
    "mutation, message",
    [
        ("identity", "underlying schedule"),
        ("reference", "Duplicate turnover reference"),
        ("count", "controls must agree"),
        ("amount", "controls must agree"),
        ("role", "return-only"),
        ("country", "registration syntax"),
        ("empty", "explicit turnover"),
        ("nested", "already composed"),
    ],
)
def test_composition_rejects_ambiguous_or_uncontrolled_populations(mutation, message):
    data, bodies = fixture()
    first, second = [bodies[str(i)] for i in data.source_ids]
    if mutation == "identity":
        second["source_identity"] = first["source_identity"]
    elif mutation == "reference":
        second["rows"][0]["reference"] = first["rows"][0]["reference"]
    elif mutation == "count":
        data.expected_rows = 3
    elif mutation == "amount":
        data.expected_amount = -data.expected_amount
    elif mutation == "role":
        second["allowed_source_roles"] = ["return"]
    elif mutation == "country":
        second["rows"][0]["registration"] = "27ABCDE1234F1Z5"
    elif mutation == "empty":
        second["rows"] = []
    else:
        second["parser_version"] = "turnover-books-composition/1"
    with pytest.raises(ValueError, match=message):
        source_rows(bodies, data, "AE")


def test_same_ledger_account_overlapping_dates_cannot_be_reallocated_to_another_registration():
    data, bodies = fixture(ledger=True)
    first, second = [bodies[str(i)] for i in data.source_ids]
    second["native_metadata"] = deepcopy(first["native_metadata"])
    second["rows"][0]["registration"] = "100000000000002"
    with pytest.raises(ValueError, match="Overlapping ledger accounts"):
        source_rows(bodies, data, "AE")
    # Adjacent closed periods are disjoint even when they select the same account.
    second["native_metadata"].update(period_start="2026-07-01", period_end="2026-09-30")
    second["rows"][0].update(period_start="2026-07-01", period_end="2026-09-30")
    assert len(source_rows(bodies, data, "AE")[0]) == 2


def test_duplicate_committed_line_cannot_be_hidden_by_distinct_account_selections():
    data, bodies = fixture(ledger=True)
    first, second = [bodies[str(i)] for i in data.source_ids]
    second["rows"][0]["id"] = first["rows"][0]["id"]
    with pytest.raises(ValueError, match="journal line cannot be allocated twice"):
        source_rows(bodies, data, "AE")
