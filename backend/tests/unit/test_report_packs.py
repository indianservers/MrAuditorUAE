"""Country/layout presets cannot replace missing boxes with narrative or tolerance."""

from copy import deepcopy

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.modules.regulatory.report_packs import catalogue, manifest, validate_source
from app.modules.regulatory.report_requirements import coverage
from app.modules.regulatory.schemas import ReportTemplate
from tests.unit.test_vat_box_scope import full_filed_boxes
from tests.unit.test_vat_emirates import compare, detailed_rows


def template(layout="emirate-20", **changes):
    pack = manifest("uae-vat201-review:" + layout + "/1")
    return ReportTemplate.model_validate(
        dict(
            title="SYNTHETIC VAT201 operational report",
            category="vat",
            rationale="Retained box review scope, not filing qualification",
            requirements_pack=pack["id"],
            requirements=pack["requirements"],
            requirements_assessed=False,
            requirements_basis="",
            blocks=[
                dict(
                    key="draft",
                    title="Unmapped draft narrative",
                    kind="narrative",
                    text="Synthetic unassessed report draft",
                )
            ],
            **changes,
        )
    )


@pytest.mark.parametrize("layout,count", [("aggregate-14", 14), ("emirate-20", 20)])
def test_manifest_drafts_are_complete_but_unassessed_and_country_specific(layout, count):
    config = template(layout)
    assert len(config.requirements) == count and not coverage(config)["complete"]
    assert (
        coverage(config)["requirements_pack"]["sha256"]
        == manifest(config.requirements_pack)["sha256"]
    )
    assert catalogue("IN") == [] and catalogue("GB") == [] and len(catalogue("AE")) == 2
    assert not coverage(config)["statutory_completeness_qualified"]
    rows = detailed_rows() if layout == "emirate-20" else full_filed_boxes()
    result = compare(
        rows,
        deepcopy(rows),
        vat201_layout=layout,
        required_boxes=manifest(config.requirements_pack)["required_boxes"],
    )
    validate_source(
        manifest(config.requirements_pack), result, [r.key for r in config.requirements]
    )


@pytest.mark.parametrize("fault", ["missing", "narrative", "not-applicable", "category", "unknown"])
def test_selected_preset_cannot_be_weakened(fault):
    body = template().model_dump(mode="json")
    if fault == "missing":
        body["requirements"].pop()
    elif fault == "narrative":
        body["requirements"][0]["source_required"] = False
    elif fault == "not-applicable":
        body["requirements"][0]["disposition"] = "NOT_APPLICABLE"
    elif fault == "category":
        body["category"] = "uae-ifrs"
    else:
        body["requirements_pack"] = "unpublished-pack"
    with pytest.raises(ValidationError):
        ReportTemplate.model_validate(body)


@pytest.mark.parametrize(
    "fault",
    [
        "wrong-layout",
        "missing-row",
        "wrong-period-scope",
        "arithmetic",
        "missing-arithmetic",
        "tolerated-variance",
        "one-sided",
    ],
)
def test_source_must_prove_the_selected_complete_review_layout(fault):
    pack = manifest("uae-vat201-review:emirate-20/1")
    result = compare()
    if fault == "wrong-layout":
        result["vat201_layout"] = "custom"
    elif fault == "missing-row":
        result["rows"].pop()
    elif fault == "wrong-period-scope":
        result["rows"][0]["registration"] = "100000000000002"
    elif fault == "arithmetic":
        result["vat201_arithmetic_error_count"] = 1
    elif fault == "missing-arithmetic":
        result["vat201_arithmetic_checks"] = []
    elif fault == "tolerated-variance":
        result["rows"][0]["differences"]["tax"] = "0.01"
    else:
        result["rows"][0]["return_source_id"] = None
    with pytest.raises(HTTPException):
        validate_source(pack, result, [r["key"] for r in pack["requirements"]])
