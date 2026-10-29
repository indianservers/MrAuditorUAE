"""Context proof/version checks do not establish semantic or legal qualification."""

import uuid
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.modules.country_workflows.msme_evidence import (
    CONTRACT,
    UNRESOLVED,
    VERIFIED,
    current_contract,
    needs_context,
)
from app.modules.country_workflows.review import approval_error
from app.modules.country_workflows.schemas import SourceInput
from app.modules.intelligence.service import current

DOCUMENT = str(uuid.uuid4())
CONTEXT = {
    "evidence_version_id": DOCUMENT,
    "sha256": "a" * 64,
    "assessment": "SYNTHETIC retained supplier fact scope",
}
RECEIPT = {"type": "evidence", "id": DOCUMENT, "sha256": "a" * 64}


@pytest.mark.parametrize(
    "table,row,required",
    [
        ("msme-supplier-assessments", {"eligibility": "ELIGIBLE"}, True),
        ("msme-supplier-assessments", {"eligibility": "INELIGIBLE"}, True),
        ("msme-supplier-assessments", {"eligibility": "UNRESOLVED"}, False),
        (
            "msme-invoices",
            {"delivery_date": "2026-04-01", "acceptance_evidence_reference": "SYN"},
            True,
        ),
        ("msme-invoices", {"delivery_date": "2026-04-01"}, False),
        ("msme-invoices", {"written_objection_date": "2026-04-05"}, True),
        ("msme-invoices", {"terms_written": True, "agreed_due_date": "2026-05-01"}, True),
        ("msme-invoices", {"terms_written": True}, False),
    ],
)
def test_resolved_fact_types_require_context_while_pending_evidence_stays_unknown(
    table, row, required
):
    assert needs_context(table, [row]) is required


def source():
    return {
        "table_type": "msme-supplier-assessments",
        "rows": [{"eligibility": "ELIGIBLE"}],
        "msme_evidence_contract": CONTRACT,
        "msme_evidence_context": deepcopy(CONTEXT),
    }


def test_source_contract_requires_its_exact_protected_evidence_receipt():
    assert current_contract(source(), [RECEIPT])
    assert not current_contract(source(), [])
    assert not current_contract(source(), [{**RECEIPT, "id": str(uuid.uuid4())}])
    assert not current_contract(source(), [{**RECEIPT, "sha256": "b" * 64}])


@pytest.mark.parametrize(
    "fault",
    [
        "legacy",
        "missing-context",
        "missing-id",
        "invalid-sha",
        "missing-assessment",
        "empty-receipt",
    ],
)
def test_malformed_or_pre_contract_source_proof_never_counts_as_current(fault):
    body = source()
    receipts = [RECEIPT]
    if fault == "legacy":
        body.pop("msme_evidence_contract")
    elif fault == "missing-context":
        body.pop("msme_evidence_context")
    elif fault == "missing-id":
        body["msme_evidence_context"].pop("evidence_version_id")
    elif fault == "invalid-sha":
        body["msme_evidence_context"]["sha256"] = "not-a-digest"
    elif fault == "missing-assessment":
        body["msme_evidence_context"]["assessment"] = " "
    else:
        receipts = [{"type": "evidence"}]
    assert not current_contract(body, receipts)


def test_verified_result_needs_actual_retained_contexts_and_matching_dependencies():
    body = {
        "workflow": "india-msme-payment-timing",
        "msme_evidence_contract": CONTRACT,
        "msme_document_binding": VERIFIED,
        "retained_msme_contexts": [CONTEXT],
        "rows": [{"state": "MATCHED"}],
    }
    assert current_contract(body, [RECEIPT]) and approval_error(body) is None
    assert not current_contract(body, [])
    body["retained_msme_contexts"] = []
    assert not current_contract(body, [RECEIPT])


def test_no_context_exemption_cannot_hide_resolved_facts():
    body = {
        "workflow": "india-msme-payment-timing",
        "msme_evidence_contract": CONTRACT,
        "msme_document_binding": UNRESOLVED,
        "retained_msme_contexts": [],
        "rows": [
            {
                "retained_supplier_assessment": {"eligibility": "UNRESOLVED"},
                "retained_invoice_facts": {},
            }
        ],
    }
    assert current_contract(body, [])
    body["rows"][0]["retained_supplier_assessment"]["eligibility"] = "ELIGIBLE"
    assert not current_contract(body, [])
    assert current_contract({"workflow": "some-other-workflow", "table_type": None}, [])


def test_annual_tax_context_guard_reads_invoice_details_not_metric_comparison_rows():
    body = {
        "workflow": "india-msme-annual-tax",
        "msme_tax_contract": "india-msme-annual-tax/1",
        "msme_tax_document_binding": "NO_TAX_FACTS_CLAIMED",
        "msme_evidence_contract": CONTRACT,
        "msme_document_binding": UNRESOLVED,
        "retained_msme_contexts": [],
        "rows": [{"state": "MATCHED"}],
        "invoice_tax_details": [{"retained_supplier_assessment": {"eligibility": "ELIGIBLE"}}],
    }
    assert not current_contract(body, [])
    body["invoice_tax_details"][0]["retained_supplier_assessment"]["eligibility"] = "UNRESOLVED"
    assert current_contract(body, [])
    body.pop("msme_evidence_contract")
    assert "retained context" in approval_error(body)


@pytest.mark.parametrize(
    "kind,body",
    [
        ("workflow-source", {"table_type": "msme-invoices", "rows": []}),
        (
            "country-workflow",
            {
                "workflow": "india-msme-payment-timing",
                "review_status": "REVIEWED",
                "rows": [{"state": "MATCHED"}],
            },
        ),
    ],
)
async def test_legacy_msme_events_are_stale_before_they_can_support_new_actions(kind, body):
    tenant = uuid.uuid4()
    db = AsyncMock()
    assert not await current(
        db,
        SimpleNamespace(tenant_id=tenant),
        SimpleNamespace(tenant_id=tenant, kind=kind, body=body, dependencies=[]),
    )
    db.get.assert_not_awaited()
    if kind == "country-workflow":
        assert "retained context" in approval_error(body)


@pytest.mark.parametrize(
    "fault", ["same-file", "wrong-table", "missing-assessment", "no-selection"]
)
def test_source_input_requires_explicit_context_purpose_and_distinct_selection(fault):
    original = uuid.uuid4()
    data = dict(
        evidence_version_id=original,
        table_type="msme-invoices",
        label="SYNTHETIC source",
        expected_rows=1,
        msme_context_evidence_version_id=uuid.uuid4(),
        msme_context_assessment="SYNTHETIC retained invoice acceptance packet",
    )
    if fault == "same-file":
        data["msme_context_evidence_version_id"] = original
    elif fault == "wrong-table":
        data["table_type"] = "transactions"
    elif fault == "missing-assessment":
        data["msme_context_assessment"] = ""
    else:
        data["msme_context_evidence_version_id"] = None
    with pytest.raises(ValidationError):
        SourceInput.model_validate(data)
