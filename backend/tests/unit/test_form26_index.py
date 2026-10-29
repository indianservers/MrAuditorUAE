"""Published numbered-item coverage is not full field/calculation qualification."""

import uuid

import pytest
from pydantic import ValidationError

from app.modules.regulatory.report_packs import manifest
from app.modules.regulatory.report_requirements import coverage
from app.modules.regulatory.schemas import ReportTemplate


def test_archived_form_original_and_targeted_capture_scope_remain_unqualified():
    import hashlib
    import json
    from pathlib import Path

    from pypdf import PdfReader

    root = Path(__file__).resolve().parents[3]
    archive = json.loads(
        (root / "docs/country-workflows/legal-sources/india-msme-source-archive.json").read_text(
            encoding="utf-8"
        )
    )
    assert archive["professional_approval"] is False
    for original in archive["documents"]:
        raw = (root / original["path"]).read_bytes()
        assert len(raw) == original["size_bytes"]
        assert hashlib.sha256(raw).hexdigest() == original["sha256"]
        assert len(PdfReader(root / original["path"]).pages) == original["page_count"]
        for capture in original["captures"]:
            assert (
                hashlib.sha256((root / capture["path"]).read_bytes()).hexdigest()
                == capture["sha256"]
            )
    source = next(item for item in archive["documents"] if item["page_count"] == 33)
    for part in ("A", "B"):
        pack = manifest(f"india-form26-index:{part}/1")
        assert pack["original_pdf"]["sha256"] == source["sha256"]
        assert pack["original_pdf"]["targeted_visual_review_pages"] == [1, 5, 9]
        assert not pack["statutory_completeness_qualified"]
        assert len(pack["requirements"]) == 65
        assert "TARGETED_VISUAL_REVIEW" in pack["source_capture_status"]


def config(part="A"):
    pack = manifest(f"india-form26-index:{part}/1")
    return dict(
        title="SYNTHETIC numbered evidence index",
        category="india-tax-audit",
        rationale="Synthetic index mechanics without legal assurance",
        requirements_pack=pack["id"],
        requirements=pack["requirements"],
        tax_audit_scope=dict(
            applicability_id=str(uuid.uuid4()),
            tax_period_start="2026-04-01",
            tax_period_end="2027-03-31",
            audited_under_other_law=part == "A",
            form="26",
            audit_report_part=part,
        ),
        blocks=[
            dict(
                key="draft",
                title="SYNTHETIC unassessed index",
                kind="narrative",
                text="Synthetic index awaiting retained workpapers",
            )
        ],
    )


@pytest.mark.parametrize("part", ["A", "B"])
def test_all_numbered_items_and_schedule_groups_start_unassessed(part):
    data = ReportTemplate.model_validate(config(part))
    keys = {r.key for r in data.requirements}
    assert len(keys) == 65
    assert {f"form26.C.{n}" for n in range(1, 9)} <= keys
    assert {f"form26.D.{n}" for n in range(9, 54)} <= keys
    assert sum(k.startswith("form26.schedule.") for k in keys) == 11
    assert f"form26.report.{part}" in keys
    result = coverage(data)
    assert not result["complete"] and not result["statutory_completeness_qualified"]
    assert all(r["disposition"] == "UNASSESSED" for r in result["items"])


@pytest.mark.parametrize(
    "fault", ["wrong-part", "legacy", "missing-item", "missing-schedule", "narrative-only"]
)
def test_index_cannot_omit_items_or_escape_its_assessed_period_and_evidence_contract(fault):
    data = config()
    if fault == "wrong-part":
        data["requirements_pack"] = "india-form26-index:B/1"
        data["requirements"] = manifest(data["requirements_pack"])["requirements"]
    elif fault == "legacy":
        data["tax_audit_scope"].update(
            tax_period_start="2025-04-01",
            tax_period_end="2026-03-31",
            form="3CA-3CD",
            audit_report_part=None,
        )
    elif fault == "missing-item":
        data["requirements"] = [r for r in data["requirements"] if r["key"] != "form26.C.1"]
    elif fault == "missing-schedule":
        data["requirements"] = [
            r for r in data["requirements"] if r["key"] != "form26.schedule.gst"
        ]
    else:
        data["requirements"][0]["source_required"] = False
    with pytest.raises(ValidationError):
        ReportTemplate.model_validate(data)


def test_not_applicable_needs_explicit_assessment_and_keeps_source_required():
    data = config()
    item = next(r for r in data["requirements"] if r["key"] == "form26.schedule.gst")
    item["disposition"] = "NOT_APPLICABLE"
    parsed = ReportTemplate.model_validate(data)
    assert next(r for r in parsed.requirements if r.key == item["key"]).source_required
    assert (
        next(r for r in coverage(parsed)["items"] if r["key"] == item["key"])["status"]
        == "MISSING_COVERAGE"
    )


@pytest.mark.parametrize("key", ["form26.report.A", "form26.C.1", "form26.D.9"])
def test_selected_report_identity_and_audit_basis_cannot_be_not_applicable(key):
    data = config()
    next(r for r in data["requirements"] if r["key"] == key)["disposition"] = "NOT_APPLICABLE"
    with pytest.raises(ValidationError):
        ReportTemplate.model_validate(data)
