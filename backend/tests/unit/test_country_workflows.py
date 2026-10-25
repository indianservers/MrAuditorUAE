import csv
import io
import json
import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.catalogue import WORKFLOWS, catalogue, country_guidance
from app.modules.country_workflows.review import approval_error
from app.modules.country_workflows.schemas import SourceInput, WorkflowInput
from app.modules.country_workflows.sources import parse_csv
from app.modules.intelligence.schemas import JobInput
from tests.unit.country_workflow_cases import CASES


def parsed(table_type, rows):
    fields = list(rows[0])
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    totals = {}
    for r in rows:
        field = "amount" if "amount" in r else "tax" if "tax" in r else None
        if field:
            totals[r["currency"]] = totals.get(r["currency"], Decimal(0)) + Decimal(r[field])
    source = SourceInput(
        evidence_version_id=uuid.uuid4(),
        table_type=table_type,
        label="Synthetic controlled source",
        expected_rows=len(rows),
        control_totals=totals,
    )
    return parse_csv(buffer.getvalue().encode(), source)


@pytest.mark.parametrize("case", CASES, ids=[f"{c['id']}-{c['title']}" for c in CASES])
def test_real_world_evidence_scenario(case):
    sources = {
        role: parsed(WORKFLOWS[case["workflow"]][2][role], rows)
        for role, rows in case["sources"].items()
    }
    data = WorkflowInput(
        workflow=case["workflow"],
        source_ids={r: uuid.uuid4() for r in sources},
        as_of="2026-06-30",
        title=case["title"],
        rationale="Synthetic independently specified operational scenario",
        **case["parameters"],
    )
    expected = case["expected"]
    if "error" in expected:
        with pytest.raises(ValueError, match=expected["error"]):
            calculate(data, case["country"], sources)
        return
    result = calculate(data, case["country"], sources)
    assert result["review_status"] == "UNVERIFIED"
    assert result["professional_conclusion"] == "NOT_DETERMINED"
    assert result["statutory_calculation_qualified"] is False
    if "state" in expected:
        assert result["rows"][0]["state"] == expected["state"]
    if "tax_difference" in expected:
        assert result["rows"][0]["tax_difference"] == expected["tax_difference"]
    if "exceptions" in expected:
        assert result["exception_count"] == expected["exceptions"]
    if "blocked" in expected:
        assert result["blocked"] == expected["blocked"]
    if "stale" in expected:
        assert result["rows"][0]["stale"] == expected["stale"]
    assert result == calculate(data, case["country"], sources)
    json.dumps(result, allow_nan=False)


def test_country_catalogue_is_explicit_and_not_a_legal_certification():
    assert not next(c for c in catalogue("AE") if c["id"] == "india-gst")["available"]
    assert not next(c for c in catalogue("IN") if c["id"] == "uae-vat")["available"]
    assert next(c for c in catalogue("GB") if c["id"] == "bank-brs")["available"]
    assert all(not c["statutory_calculation_qualified"] for c in catalogue("AE"))


def test_published_scenario_catalogue_matches_executable_fixtures():
    from app.modules.country_workflows.catalogue import scenarios

    assert len(scenarios()) == 148
    assert scenarios() == [
        {k: c[k] for k in ["id", "title", "workflow", "country", "expected"]} for c in CASES
    ]


def test_unicode_bank_party_names_remain_distinct():
    from tests.unit.country_workflow_cases import transaction

    data = WorkflowInput(
        workflow="bank-brs",
        source_ids={"books": uuid.uuid4(), "statement": uuid.uuid4()},
        as_of="2026-06-30",
        title="Arabic bank test",
        rationale="Verify distinct Arabic counterparties",
        account="BANK-1",
        book_opening="0",
        book_closing="100",
        statement_opening="0",
        statement_closing="100",
    )
    sources = {
        role: parsed("transactions", [transaction(id=role, reference="مرجع", counterparty=party)])
        for role, party in [("books", "أحمد"), ("statement", "محمد")]
    }
    result = calculate(data, "AE", sources)
    assert result["matches"] == [] and result["exception_count"] == 2
    sources["statement"] = parsed(
        "transactions", [transaction(id="statement", reference="مرجع", counterparty="أحمد")]
    )
    assert calculate(data, "AE", sources)["exception_count"] == 0


def test_payment_cannot_extend_its_own_expected_due_date():
    from tests.unit.country_workflow_cases import obligation

    sources = {
        r: parsed("obligations", [obligation(id=r)]) for r in ["expected", "return", "payment"]
    }
    sources["payment"] = parsed(
        "obligations", [obligation(id="payment", due_date="2026-06-20", payment_date="2026-06-10")]
    )
    data = WorkflowInput(
        workflow="statutory-dues",
        source_ids={r: uuid.uuid4() for r in sources},
        as_of="2026-06-30",
        title="Due date test",
        rationale="Expected obligation due date must remain authoritative",
    )
    assert calculate(data, "AE", sources)["rows"][0]["state"] == "DUE_DATE_DIFFERENCE"


def test_tax_audit_transition_uses_tax_year_start_not_current_run_date():
    assert country_guidance("IN", date(2026, 10, 24))["tax_reporting"] == "PENDING_TAX_YEAR_START"
    assert country_guidance("IN", date(2026, 10, 24), date(2025, 4, 1))["tax_reporting"].startswith(
        "Legacy"
    )
    assert country_guidance("IN", date(2026, 10, 24), date(2026, 4, 1))["tax_reporting"].startswith(
        "Form 26"
    )
    assert country_guidance("IN", date(2025, 3, 31))["tcs_206c_1h"].startswith("HISTORICAL")
    assert country_guidance("IN", date(2025, 4, 1))["tcs_206c_1h"] == "WITHDRAWN"


@pytest.mark.parametrize(
    "country,workflow",
    [
        ("AE", "india-gst"),
        ("IN", "uae-vat"),
        ("AE", "india-withholding"),
        ("US", "payroll-settlement"),
    ],
)
def test_illegal_country_workflow_combinations_are_rejected(country, workflow):
    data = WorkflowInput(
        workflow=workflow,
        source_ids={"books": uuid.uuid4()},
        as_of="2026-06-30",
        title="Synthetic test",
        rationale="Synthetic scope verification",
    )
    with pytest.raises(ValueError, match="engagement country"):
        calculate(data, country, {})


def test_independent_sources_required_even_when_label_differs():
    identifier = uuid.uuid4()
    with pytest.raises(ValueError, match="independent source"):
        WorkflowInput(
            workflow="uae-vat",
            source_ids={"books": identifier, "return": identifier},
            as_of="2026-06-30",
            title="Synthetic test",
            rationale="Synthetic scope verification",
        )


def test_csv_control_count_totals_duplicate_id_and_sensitive_error():
    controls = SourceInput(
        evidence_version_id=uuid.uuid4(),
        table_type="transactions",
        label="Synthetic source",
        expected_rows=1,
        control_totals={"AED": "100"},
    )
    head = b"id,account,reference,date,currency,amount\n"
    row = b"1,BANK-1,ref,2026-06-01,AED,100\n"
    assert parse_csv(head + row, controls)["row_count"] == 1
    for content, error in [
        (head + row + row, "Duplicate source"),
        (head + row.replace(b"100", b"90"), "control totals"),
        (head, "row-count"),
        (head.replace(b"amount", b"id") + row, "Duplicate, empty"),
    ]:
        with pytest.raises(ValueError, match=error):
            parse_csv(content, controls)
    with pytest.raises(ValueError) as exc:
        parse_csv(head + row.replace(b"100", b"PRIVATE-BANK-DATA"), controls)
    assert "PRIVATE-BANK-DATA" not in str(exc.value)


def test_nonfinite_amount_and_positive_credit_note_rejected():
    from tests.unit.country_workflow_cases import document, transaction

    with pytest.raises(ValueError):
        parsed("transactions", [transaction(amount="NaN")])
    with pytest.raises(ValueError):
        parsed("transactions", [transaction(amount="Infinity")])
    with pytest.raises(ValueError):
        parsed("tax-documents", [document(document_type="credit-note")])


def test_exception_acknowledgment_cannot_override_missing_evidence():
    assert approval_error({"blocked": True, "rows": []})
    assert approval_error({"blocked": False, "rows": [{"state": "VARIANCE"}]})
    assert (
        approval_error(
            {
                "blocked": False,
                "rows": [{"state": "VARIANCE", "auditor_status": "EXCEPTION_DOCUMENTED"}],
            }
        )
        is None
    )


def test_new_operations_are_validated_at_queue_submission():
    with pytest.raises(ValueError):
        JobInput(operation="country-workflow", payload={"workflow": "india-gst"})
    with pytest.raises(ValueError):
        JobInput(operation="workflow-source", payload={"table_type": "untrusted-code"})


def test_declared_nil_inventory_is_distinct_from_missing_source():
    from app.modules.country_workflows.schemas import Stock

    header = (",".join(Stock.model_fields) + "\n").encode()
    controls = SourceInput(
        evidence_version_id=uuid.uuid4(),
        table_type="stock",
        label="Synthetic nil inventory",
        expected_rows=0,
        nil_reason="No inventory held in either warehouse under the scoped declaration",
    )
    source = parse_csv(header, controls)
    data = WorkflowInput(
        workflow="stock-audit",
        source_ids={"books": uuid.uuid4(), "count": uuid.uuid4()},
        as_of="2026-06-30",
        title="Nil inventory review",
        rationale="Independent nil inventory evidence declarations",
    )
    result = calculate(data, "AE", {"books": source, "count": source})
    assert result["nil_population"] and len(result["nil_declarations"]) == 2
    assert result["coverage"]["percent"] is None
    assert result["review_status"] == "UNVERIFIED"
    with pytest.raises(ValueError):
        SourceInput(
            evidence_version_id=uuid.uuid4(),
            table_type="stock",
            label="Missing inventory",
            expected_rows=0,
        )


def test_nil_bank_source_requires_zero_movement_controls():
    from app.modules.country_workflows.schemas import Transaction

    header = (",".join(Transaction.model_fields) + "\n").encode()
    controls = SourceInput(
        evidence_version_id=uuid.uuid4(),
        table_type="transactions",
        label="Synthetic inactive bank account",
        expected_rows=0,
        nil_reason="No movements in the independently declared bank population",
        control_totals={"AED": "0"},
    )
    source = parse_csv(header, controls)
    data = WorkflowInput(
        workflow="bank-brs",
        source_ids={"books": uuid.uuid4(), "statement": uuid.uuid4()},
        as_of="2026-06-30",
        title="Inactive account",
        rationale="Independently review zero movement source declarations",
        account="BANK-1",
        book_opening="100",
        book_closing="100",
        statement_opening="100",
        statement_closing="100",
    )
    assert calculate(data, "AE", {"books": source, "statement": source})["blocked"] is False
    with pytest.raises(ValueError, match="nonzero"):
        parse_csv(header, controls.model_copy(update={"control_totals": {"AED": Decimal("1")}}))


@pytest.mark.parametrize(
    "component,country,period",
    [("PF", "AE", "2026-05"), ("PT", "AE", "2026-05"), ("TCS:206C(1H)", "IN", "2025-04")],
)
def test_country_and_withdrawn_components_do_not_produce_liabilities(component, country, period):
    from tests.unit.country_workflow_cases import obligation

    sources = {
        r: parsed("obligations", [obligation(id=r, component=component, period=period)])
        for r in ["expected", "return", "payment"]
    }
    data = WorkflowInput(
        workflow="statutory-dues",
        source_ids={r: uuid.uuid4() for r in sources},
        as_of="2026-06-30",
        title="Synthetic test",
        rationale="Synthetic country safeguards",
    )
    with pytest.raises(ValueError):
        calculate(data, country, sources)
