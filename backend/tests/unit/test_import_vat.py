import csv
import io
import uuid
from copy import deepcopy

import pytest

from app.modules.country_workflows.schemas import SourceInput
from app.modules.country_workflows.sources import parse_csv
from tests.unit.test_shared_audit_workflows import run


def line(**changes):
    return {
        "id": "IMPORT-1",
        "registration": "100000000000001",
        "customs_registration": "SYN-CRN",
        "authority": "SYNTHETIC-DXB",
        "declaration": "DECL-1",
        "line_reference": "1",
        "entry_kind": "declaration",
        "adjustment_reference": "",
        "record_version": "1",
        "version_status": "current",
        "period_start": "2026-04-01",
        "period_end": "2026-06-30",
        "date": "2026-06-10",
        "currency": "AED",
        "net": "1000",
        "tax": "50",
        "evidence_reference": "SYNTHETIC-RETAINED-SOURCE",
        "assessment": "Synthetic assessed import detail only; no legal conclusion",
        **changes,
    }


def populations(rows=None):
    return {role: deepcopy(rows or [line()]) for role in ("customs", "portal", "books")}


def test_import_declarations_and_signed_adjustments_remain_separate():
    tables = populations(
        [
            line(),
            line(
                id="ADJ-1",
                entry_kind="adjustment",
                adjustment_reference="ADJ-1",
                net="-100",
                tax="-5",
            ),
        ]
    )
    output = run("uae-import-vat", tables)
    assert output["exception_count"] == 0 and not output["blocked"]
    assert {row["vat201_box"] for row in output["rows"]} == {"6", "7"}
    assert output["role_totals"]["customs"]["declaration"]["net"] == "1000"
    assert output["role_totals"]["customs"]["adjustment"]["net"] == "-100"
    assert output["professional_conclusion"] == "NOT_DETERMINED"


def test_opposing_declaration_variances_cannot_cancel_at_total_level():
    tables = populations([line(), line(id="IMPORT-2", declaration="DECL-2")])
    tables["portal"][0]["tax"], tables["portal"][1]["tax"] = "55", "45"
    output = run("uae-import-vat", tables)
    assert output["exception_count"] == 2
    assert all("PORTAL_VALUE_DIFFERENCE" in row["exceptions"] for row in output["rows"])


def test_superseded_values_remain_visible_without_entering_current_totals():
    tables = populations(
        [line(id="OLD", record_version="0", version_status="superseded", tax="500"), line()]
    )
    output = run("uae-import-vat", tables)
    assert output["exception_count"] == 0
    assert output["role_totals"]["customs"]["declaration"]["tax"] == "50"
    assert len(output["rows"][0]["source_versions"]["customs"]) == 2


@pytest.mark.parametrize("status", ["superseded", "cancelled"])
def test_absent_current_version_is_unresolved_not_zero(status):
    tables = populations()
    tables["customs"][0]["version_status"] = status
    output = run("uae-import-vat", tables)
    assert output["blocked"]
    assert output["role_totals"]["customs"]["declaration"]["tax"] is None
    assert output["rows"][0]["differences"]["portal"]["tax"] is None


def test_multiple_current_versions_cannot_be_added_or_selected_arbitrarily():
    tables = populations()
    tables["customs"].append(line(id="DUPLICATE", record_version="2"))
    output = run("uae-import-vat", tables)
    assert (
        output["blocked"]
        and "CUSTOMS_CURRENT_VERSION_UNRESOLVED" in output["rows"][0]["exceptions"]
    )


def test_absent_adjustment_population_is_not_an_asserted_nil_box7():
    output = run("uae-import-vat", populations())
    assert output["role_totals"]["portal"]["adjustment"]["tax"] is None
    assert output["role_totals"]["portal"]["adjustment"]["selected_rows"] == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("net", "-1"),
        ("currency", "INR"),
        ("registration", "123"),
        ("date", "2026-07-01"),
        ("authority", " "),
    ],
)
def test_invalid_import_scope_is_rejected(field, value):
    with pytest.raises(ValueError):
        run("uae-import-vat", populations([line(**{field: value})]))


def test_mixed_registrations_periods_and_future_periods_are_rejected():
    for extra in (
        line(id="OTHER", registration="100000000000002"),
        line(id="OTHER", period_start="2026-06-01"),
    ):
        with pytest.raises(ValueError, match="one VAT registration"):
            run("uae-import-vat", populations([line(), extra]))
    with pytest.raises(ValueError, match="closes after"):
        run("uae-import-vat", populations(), as_of="2026-06-29")


def test_customs_registration_and_authority_do_not_cross_match():
    tables = populations()
    tables["portal"][0]["customs_registration"] = "OTHER"
    output = run("uae-import-vat", tables)
    assert len(output["rows"]) == 2 and output["exception_count"] == 2


def test_date_differences_are_reviewed_even_when_amounts_match():
    tables = populations()
    tables["books"][0]["date"] = "2026-06-11"
    output = run("uae-import-vat", tables)
    assert "BOOKS_DATE_DIFFERENCE" in output["rows"][0]["exceptions"]


def test_late_reported_import_keeps_its_original_date_and_timing_exception():
    output = run("uae-import-vat", populations([line(date="2026-03-31")]))
    assert output["exception_count"] == 1
    assert "PORTAL_DATE_OUTSIDE_ASSESSED_PERIOD" in output["rows"][0]["exceptions"]
    assert output["rows"][0]["source_versions"]["customs"][0]["date"] == "2026-03-31"


def test_independent_taxable_base_is_mandatory_and_checked_separately_from_tax():
    params = dict(
        evidence_version_id=uuid.uuid4(),
        table_type="import-vat-lines",
        label="SYNTHETIC import",
        expected_rows=1,
        control_totals={"AED": "50"},
    )
    with pytest.raises(ValueError, match="independent AED taxable-base"):
        SourceInput(**params)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(line()))
    writer.writeheader()
    writer.writerow(line())
    with pytest.raises(ValueError, match="taxable-base control does not agree"):
        parse_csv(
            buffer.getvalue().encode(), SourceInput(**params, import_taxable_base_control="999")
        )
    assert (
        parse_csv(
            buffer.getvalue().encode(), SourceInput(**params, import_taxable_base_control="1000")
        )["import_taxable_base_control"]
        == "1000"
    )
