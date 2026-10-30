"""UAE VAT reporting currency is separate from original foreign invoice evidence."""

import uuid
from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.review import approval_error
from app.modules.country_workflows.schemas import WorkflowInput
from app.modules.country_workflows.uae_vat_currency import current
from app.modules.intelligence.service import current as event_current
from tests.unit.country_workflow_cases import document
from tests.unit.test_country_workflows import parsed


def fixture(**changes):
    role = "return"
    data = WorkflowInput(
        workflow="uae-vat",
        source_ids={r: uuid.uuid4() for r in ["books", role]},
        as_of="2026-06-30",
        title="SYNTHETIC currency control",
        rationale="Synthetic reporting-currency comparison mechanics",
        currency="AED",
        **changes,
    )
    sources = {
        r: parsed("tax-documents", [document(id=r, currency="AED", component="VAT")])
        for r in ["books", role]
    }
    return data, sources


@pytest.mark.parametrize("role", ["books", "return", "both"])
@pytest.mark.parametrize("currency", ["INR", "USD", "EUR"])
def test_each_foreign_reporting_population_is_rejected_without_conversion(role, currency):
    data, sources = fixture()
    for selected_role in ["books", "return"] if role == "both" else [role]:
        sources[selected_role]["rows"][0]["currency"] = currency
    with pytest.raises(ValueError, match="requires AED reporting amounts"):
        calculate(data, "AE", sources)


def test_aed_compares_exactly_and_preserves_original_source_populations():
    data, sources = fixture()
    original = deepcopy(sources)
    result = calculate(data, "AE", sources)
    assert result["rows"][0]["state"] == "MATCHED" and result["vat_reporting_currency"] == "AED"
    assert current(result) and approval_error(result) is None
    assert sources == original
    data.currency = "USD"
    with pytest.raises(ValueError, match="requires AED reporting amounts"):
        calculate(data, "AE", sources)


@pytest.mark.parametrize("fault", ["contract", "currency", "parameter", "rows", "null-parameters"])
async def test_legacy_or_malformed_comparison_is_stale_and_not_approvable_without_rewriting(fault):
    data, sources = fixture()
    body = calculate(data, "AE", sources)
    if fault == "contract":
        body.pop("vat_reporting_currency_contract")
    elif fault == "currency":
        body["rows"][0]["currency"] = "USD"
    elif fault == "parameter":
        body["parameters"]["currency"] = "USD"
    elif fault == "rows":
        body["rows"] = None
    else:
        body["parameters"] = None
    original = deepcopy(body)
    tenant = uuid.uuid4()
    assert not current(body) and "AED reporting controls" in approval_error(body)
    assert not await event_current(
        None,
        SimpleNamespace(tenant_id=tenant),
        SimpleNamespace(tenant_id=tenant, kind="country-workflow", body=body),
    )
    assert body == original


def test_explicit_nil_reporting_populations_retain_the_aed_contract_without_inventing_rows():
    from app.modules.country_workflows.schemas import SourceInput, TaxDocument
    from app.modules.country_workflows.sources import parse_csv

    data, _ = fixture()
    source = parse_csv(
        (",".join(TaxDocument.model_fields) + "\n").encode(),
        SourceInput(
            evidence_version_id=uuid.uuid4(),
            table_type="tax-documents",
            label="SYNTHETIC nil reporting documents",
            expected_rows=0,
            nil_reason="Synthetic separately assessed nil reporting population, not a complete VAT return",
        ),
    )
    result = calculate(data, "AE", {"books": source, "return": source})
    assert result["rows"] == [] and result["nil_population"]
    assert current(result) and result["vat_reporting_currency"] == "AED"
    assert result["statutory_calculation_qualified"] is False
