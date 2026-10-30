"""Check shipped synthetic upload examples against their literal expectations."""

import json
from pathlib import Path
from uuid import uuid4

import pytest

from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.schemas import SourceInput, WorkflowInput
from app.modules.country_workflows.sources import parse_csv


@pytest.mark.parametrize("country", ["AE", "IN"])
def test_shipped_fifo_examples_use_the_actual_shared_packet_parser(country):
    folder = (
        Path(__file__).resolve().parents[3]
        / "docs/country-workflows/sample-inputs/SYNTHETIC-inventory-fifo"
        / country
    )
    fixture = json.loads((folder / "controls-and-expectations.json").read_text(encoding="utf-8"))
    assert fixture["synthetic_only"] is True and fixture["real_client_validation"] is False
    document = str(uuid4())
    sources = {}
    for role, name in (("movements", "movements.csv"), ("books", "closing-books.csv")):
        data = SourceInput.model_validate(
            {
                "evidence_version_id": str(uuid4()),
                "label": "SYNTHETIC shipped upload example",
                **fixture["movements_source" if role == "movements" else "books_source"],
                **({"rule_document_version_id": document} if role == "movements" else {}),
            }
        )
        sources[role] = parse_csv(
            (folder / name).read_bytes(),
            data,
            {"source_evidence_version_id": document, "source_sha256": "a" * 64}
            if role == "movements"
            else None,
        )
    data = WorkflowInput.model_validate(
        {
            **fixture["workflow"],
            "source_ids": {role: str(uuid4()) for role in sources},
            "title": "SYNTHETIC shipped FIFO example",
            "rationale": "Verify literal controls and expected example arithmetic",
        }
    )
    out = calculate(data, country, sources)
    expected = fixture["literal_expected_arithmetic"]
    for field in (
        "expected_closing_quantity",
        "raw_fifo_closing_cost",
        "covered_issue_cost",
        "raw_cost_rollforward_difference",
    ):
        assert out["rows"][0][field] == expected[field]
    assert [row["cost"] for row in out["fifo_allocations"]] == expected["allocation_costs"]
    assert out["blocked"] is expected["blocked"]
    assert out["statutory_calculation_qualified"] is False
    assert all(
        row["source_evidence_version_id"] == document for row in sources["movements"]["rows"]
    )
