"""Synthetic technical fixtures; no UAE legal or accounting conclusions."""

import hashlib
import uuid
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from app.core.engine_contracts import EngineIssue, EngineResult
from app.modules.intelligence import service
from app.modules.intelligence.documents import money, structured


def test_arabic_english_fields_preserve_source_and_do_not_invent_confidence():
    text = "المورد: شركة اصطناعية\nرقم الفاتورة: INV-١٢\nتاريخ الفاتورة: ٢٠٢٦-٠١-٣١\nالمبلغ الإجمالي: (١٬٢٠٠٫٥٠)\nالعملة: AED\n"
    result = structured(
        [{"page": 2, "provider": "pdfium-text", "blocks": [{"id": "p2-b0", "text": text}]}], "AE"
    )
    assert result["fields"]["gross_amount"] == "-1200.50"
    assert result["fields"]["invoice_number"] == "INV-12"
    assert result["fields"]["document_date"] == "2026-01-31"
    location = result["field_locations"]["gross_amount"]
    assert "١٬٢٠٠٫٥٠" in location["raw_text"]
    assert location["page"] == 2 and location["confidence"] is None
    assert result["fields"]["tax_amount"] is None
    conflicting = structured(
        [{"page": 1, "blocks": [{"id": "b", "text": "Gross Amount: 100\nالمبلغ الإجمالي: ٢٠٠"}]}],
        "AE",
    )
    assert conflicting["fields"]["gross_amount"] is None
    assert conflicting["validation_messages"]


@pytest.mark.parametrize("value", ["1,20.00", "NaN", "Infinity", "1.000000001", "(12", "--12"])
def test_malformed_money_is_not_a_success(value):
    with pytest.raises(ValueError):
        money(value)


def test_ambiguous_date_requires_selected_convention():
    pages = [{"page": 1, "blocks": [{"id": "b", "text": "Invoice Date: 03/04/2026"}]}]
    assert structured(pages, "AE")["fields"]["document_date"] is None
    assert structured(pages, "AE", date_format="dmy")["fields"]["document_date"] == "2026-04-03"
    assert structured(pages, "AE", date_format="mdy")["fields"]["document_date"] == "2026-03-04"


async def test_unknown_dependency_is_stale_and_foreign_tenant_is_not_current(monkeypatch):
    tenant = uuid.uuid4()
    obj = SimpleNamespace(
        id=uuid.uuid4(), tenant_id=tenant, version=1, dependencies=[{"type": "unknown-v99"}]
    )

    async def head(*args):
        return 1

    monkeypatch.setattr(service, "head", head)
    assert not await service.current(None, SimpleNamespace(tenant_id=tenant), obj)
    assert not await service.current(None, SimpleNamespace(tenant_id=uuid.uuid4()), obj)


def test_execution_completeness_severity_and_review_are_independent():
    result = EngineResult(
        **{k: uuid.uuid4() for k in ["tenant_id", "entity_id", "engagement_id", "period_id"]},
        jurisdiction="AE",
        framework="IFRS",
        calculation_version="synthetic/1",
        completeness="partial",
        issues=[
            EngineIssue(code="missing_evidence", reason="No source", remediation="Obtain source")
        ],
    )
    assert result.execution_status == "succeeded"
    assert result.review_status == "UNVERIFIED"
    assert result.issues[0].blocking


def test_supporting_table_rejects_non_iso_currency(tmp_path, monkeypatch):
    path = tmp_path / "synthetic.csv"
    path.write_text("reference,currency,amount,date\nSYNTHETIC,ZZZ,100,2026-01-31\n")

    @contextmanager
    def local(*args):
        yield path

    monkeypatch.setattr(service, "ObjectStore", lambda: SimpleNamespace(local=local))
    version = SimpleNamespace(
        media_type="text/csv",
        object_key="synthetic",
        object_version="1",
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    with pytest.raises(ValueError, match="Invalid currency"):
        service.read_table(version, "bank", ".", "iso")


def test_extraction_limits_are_enforced_before_worker_creation(tmp_path, monkeypatch):
    from app.modules.intelligence.documents import extract_document, preview_page

    path = tmp_path / "synthetic.pdf"
    path.write_bytes(b"x" * 2048)
    monkeypatch.setattr(
        "app.core.config.settings",
        lambda: SimpleNamespace(document_max_bytes=1024, document_max_pages=1),
    )
    with pytest.raises(ValueError, match="configured byte limit"):
        extract_document(path, "application/pdf", "AE")
    with pytest.raises(ValueError, match="Page numbers start at one"):
        preview_page(path, "application/pdf", 0)


async def test_capture_rejects_known_cross_engagement_sources():
    from fastapi import HTTPException

    from app.modules.lineage.working_papers import capture

    source = SimpleNamespace(id=uuid.uuid4(), engagement_id=uuid.uuid4(), version=1)
    selections = iter([[source], [], []])

    async def scalars(*args):
        rows = next(selections)
        return SimpleNamespace(all=lambda: rows)

    obj = SimpleNamespace(
        id=uuid.uuid4(), engagement_id=uuid.uuid4(), body={"source": str(source.id)}
    )
    with pytest.raises(HTTPException) as error:
        await capture(
            SimpleNamespace(scalars=scalars), SimpleNamespace(tenant_id=uuid.uuid4()), obj
        )
    assert error.value.status_code == 422
