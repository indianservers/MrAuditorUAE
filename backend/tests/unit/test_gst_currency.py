"""GST reporting currency is separate from original foreign invoice evidence."""

import uuid
from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.gst_currency import current
from app.modules.country_workflows.review import approval_error
from app.modules.country_workflows.schemas import WorkflowInput
from app.modules.intelligence.service import current as event_current
from tests.unit.country_workflow_cases import document
from tests.unit.test_country_workflows import parsed


def fixture(workflow="india-gst", **changes):
    role = "invoices" if workflow == "india-invoice-register" else "return"
    data = WorkflowInput(
        workflow=workflow,
        source_ids={r: uuid.uuid4() for r in ["books", role]},
        as_of="2026-06-30",
        title="SYNTHETIC currency control",
        rationale="Synthetic reporting-currency comparison mechanics",
        currency="INR",
        **changes,
    )
    sources = {
        r: parsed("tax-documents", [document(id=r, currency="INR", component="CGST")])
        for r in ["books", role]
    }
    return data, sources


@pytest.mark.parametrize("role", ["books", "return", "both"])
@pytest.mark.parametrize("currency", ["AED", "USD", "EUR"])
@pytest.mark.parametrize("workflow", ["india-gst", "india-gstr1-documents"])
def test_each_foreign_reporting_population_is_rejected_without_conversion(workflow, role, currency):
    data, sources = fixture(workflow)
    for selected_role in ["books", "return"] if role == "both" else [role]:
        sources[selected_role]["rows"][0]["currency"] = currency
    with pytest.raises(ValueError, match="requires INR reporting amounts"):
        calculate(data, "IN", sources)


@pytest.mark.parametrize("workflow", ["india-gst", "india-gstr1-documents"])
def test_inr_compares_exactly_and_preserves_original_source_populations(workflow):
    data, sources = fixture(workflow)
    original = deepcopy(sources)
    result = calculate(data, "IN", sources)
    assert result["rows"][0]["state"] == "MATCHED" and result["gst_reporting_currency"] == "INR"
    assert current(result) and approval_error(result) is None
    assert sources == original
    data.currency = "AED"
    with pytest.raises(ValueError, match="requires INR"):
        calculate(data, "IN", sources)


def test_foreign_original_invoice_comparison_stays_available_as_a_distinct_workflow():
    data, sources = fixture("india-invoice-register", invoice_direction="purchase")
    for population in sources.values():
        population["rows"][0]["currency"] = "USD"
    result = calculate(data, "IN", sources)
    assert result["rows"][0]["state"] == "MATCHED"
    assert result["rows"][0]["currency"] == "USD"
    assert "gst_reporting_currency_contract" not in result


@pytest.mark.parametrize("fault", ["contract", "currency", "parameter", "rows", "null-parameters"])
@pytest.mark.parametrize("workflow", ["india-gst", "india-gstr1-documents"])
async def test_legacy_or_malformed_comparison_is_stale_and_not_approvable_without_rewriting(
    workflow, fault
):
    data, sources = fixture(workflow)
    body = calculate(data, "IN", sources)
    if fault == "contract":
        body.pop("gst_reporting_currency_contract")
    elif fault == "currency":
        body["rows"][0]["currency"] = "AED"
    elif fault == "parameter":
        body["parameters"]["currency"] = "AED"
    elif fault == "rows":
        body["rows"] = None
    else:
        body["parameters"] = None
    original = deepcopy(body)
    tenant = uuid.uuid4()
    assert not current(body) and "INR reporting controls" in approval_error(body)
    assert not await event_current(
        None,
        SimpleNamespace(tenant_id=tenant),
        SimpleNamespace(tenant_id=tenant, kind="country-workflow", body=body),
    )
    assert body == original


@pytest.mark.parametrize("workflow", ["india-gst", "india-gstr1-documents"])
def test_explicit_nil_reporting_populations_retain_the_inr_contract_without_inventing_rows(
    workflow,
):
    from app.modules.country_workflows.schemas import SourceInput, TaxDocument
    from app.modules.country_workflows.sources import parse_csv

    data, _ = fixture(workflow)
    source = parse_csv(
        (",".join(TaxDocument.model_fields) + "\n").encode(),
        SourceInput(
            evidence_version_id=uuid.uuid4(),
            table_type="tax-documents",
            label="SYNTHETIC nil reporting documents",
            expected_rows=0,
            nil_reason="Synthetic separately assessed nil reporting population, not a complete GST return",
        ),
    )
    result = calculate(data, "IN", {"books": source, "return": source})
    assert result["rows"] == [] and result["nil_population"]
    assert current(result) and result["gst_reporting_currency"] == "INR"
    assert result["statutory_calculation_qualified"] is False


def test_native_outward_return_cannot_compare_foreign_books_under_an_inr_parameter():
    from tests.unit.test_india_gstr1_source import books, workflow
    from tests.unit.test_india_gstr1_source import parsed as native_return

    population = books()
    for row in population["rows"]:
        row["currency"] = "USD"
    with pytest.raises(ValueError, match="requires INR reporting amounts"):
        calculate(workflow(), "IN", {"books": population, "return": native_return()})
