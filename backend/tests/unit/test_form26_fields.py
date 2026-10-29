"""Source-specific field coverage and retained exact-version scope controls."""

import hashlib
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.modules.regulatory.form26_index import manifest
from app.modules.regulatory.report_requirements import coverage
from app.modules.regulatory.schemas import ReportTemplate
from app.modules.regulatory.workpaper_report_scope import WorkpaperReportScope, require_mapping
from tests.unit.test_form26_index import config
from tests.unit.test_workpaper_report_scope import paper, report


@pytest.mark.parametrize("part", ["A", "B"])
def test_published_fields_are_explicit_unique_source_bound_and_unassessed(part):
    pack = manifest(f"india-form26-index:{part}/2")
    data = config(part)
    data.update(requirements_pack=pack["id"], requirements=deepcopy(pack["requirements"]))
    parsed = ReportTemplate.model_validate(data)
    assert len(parsed.requirements) == 877
    fields = {f["key"]: f for f in pack["fields"]}
    assert len(fields) == len(pack["requirements"])
    assert all(1 <= f["page"] <= 33 for f in fields.values())
    assert all(r.disposition == "UNASSESSED" and r.source_required for r in parsed.requirements)
    assert not coverage(parsed)["complete"]
    assert not pack["statutory_completeness_qualified"]
    assert not pack["field_mapping_professionally_qualified"]
    assert pack["visual_inventory_pages"] == list(range(1, 34))
    assert len(manifest(f"india-form26-index:{part}/1")["requirements"]) == 65
    original = Path(__file__).resolve().parents[3] / pack["original_pdf"]["path"]
    assert hashlib.sha256(original.read_bytes()).hexdigest() == pack["original_pdf"]["sha256"]
    assert all(
        f["key"] not in pack["not_applicable_keys"] for f in fields.values() if f["mandatory"]
    )


def test_continuations_fixed_cells_and_omitted_text_tables_are_present():
    pack = manifest("india-form26-index:A/2")
    fields = {f["key"].removeprefix("form26.field."): f for f in pack["fields"]}
    assert len([k for k in fields if k.startswith("schedule.36.plant.")]) == 19 * 4
    assert len([k for k in fields if k.startswith("schedule.36.other.")]) == 16 * 7
    assert fields["schedule.36.plant.21.p45"]["page"] == 24
    assert fields["schedule.36.other.18.ships"]["page"] == 25
    assert "viii" in fields["schedule.36.other.18.ships"]["title"]
    assert fields["schedule.17.11.net"]["page"] == 16
    assert fields["schedule.20.13.amount"]["page"] == 17
    assert fields["schedule.27c.1.amount"]["page"] == 18
    assert fields["schedule.50b.c7"]["page"] == 30
    assert "Unreported transaction amount" in fields["schedule.50b.c7"]["title"]
    assert "398(3)(a)" in fields["schedule.50c.c2"]["title"]
    assert "Registration/identification" in fields["schedule.52a.c3"]["title"]
    for ref, count in [("53a", 13), ("53bi", 17), ("53bii", 15)]:
        assert len([k for k in fields if k.startswith(f"schedule.{ref}.c")]) == count
        assert "Unit name" in fields[f"schedule.{ref}.c3"]["title"]
    codes = pack["transaction_codes_note_8"]
    assert codes["page"] == 13 and list(codes["values"]) == list("ABCDEFGHIJKL")
    assert not codes["automatically_classified"]
    assert "MAIN 20" in fields["D.20"]["title"]
    assert "92(2)(m)" in fields["schedule.21.c7"]["title"]
    assert fields["source_review.income_numbering_conflict"]["mandatory"]


@pytest.mark.parametrize(
    "fault",
    ["missing", "duplicate", "unprotected", "wrong-part", "custom-overflow", "mandatory-na"],
)
def test_expanded_scope_cannot_drop_fields_or_expand_other_report_scopes(fault):
    pack = manifest("india-form26-index:A/2")
    data = config()
    data.update(requirements_pack=pack["id"], requirements=deepcopy(pack["requirements"]))
    if fault == "missing":
        data["requirements"].pop()
    elif fault == "duplicate":
        data["requirements"].append(deepcopy(data["requirements"][0]))
    elif fault == "unprotected":
        data["requirements"][-1]["source_required"] = False
    elif fault == "wrong-part":
        data["tax_audit_scope"]["audit_report_part"] = "B"
    elif fault == "custom-overflow":
        data["requirements_pack"] = None
    else:
        next(
            r
            for r in data["requirements"]
            if r["key"] == "form26.field.source_review.income_numbering_conflict"
        )["disposition"] = "NOT_APPLICABLE"
    with pytest.raises(ValidationError):
        ReportTemplate.model_validate(data)


def test_new_fields_require_new_exact_workpaper_version_and_keep_per_paper_bound():
    pack = manifest("india-form26-index:A/2")
    data = config()
    data.update(requirements_pack=pack["id"], requirements=deepcopy(pack["requirements"]))
    key = "form26.field.schedule.52a.c3"
    next(r for r in data["requirements"] if r["key"] == key)["disposition"] = "REQUIRED"
    body = paper(key)
    body["report_requirement_scope"]["preset_id"] = pack["id"]
    _, block = report()
    block.requirement_keys = [key]
    require_mapping(ReportTemplate.model_validate(data), block, body)
    scope = body["report_requirement_scope"]
    scope["items"] = [{**scope["items"][0], "key": r["key"]} for r in pack["requirements"][:101]]
    with pytest.raises(ValidationError):
        WorkpaperReportScope.model_validate(scope)
    scope["items"] = scope["items"][:100]
    assert len(WorkpaperReportScope.model_validate(scope).items) == 100
    scope["preset_id"] = "india-form26-index:A/1"
    with pytest.raises(ValidationError):
        WorkpaperReportScope.model_validate(scope)


@pytest.mark.parametrize(
    "method,path,expanded",
    [
        (
            "POST",
            "/api/v1/regulatory/engagements/00000000-0000-0000-0000-000000000001/report-templates",
            True,
        ),
        (
            "PATCH",
            "/api/v1/regulatory/engagements/00000000-0000-0000-0000-000000000001/report-templates",
            False,
        ),
        (
            "POST",
            "/api/v1/regulatory/engagements/00000000-0000-0000-0000-000000000001/reports",
            False,
        ),
        (
            "POST",
            "/api/v1/regulatory/engagements/00000000-0000-0000-0000-000000000001/report-templates/extra",
            False,
        ),
        ("POST", "/api/v1/regulatory/engagements/invalid/report-templates", False),
        ("POST", "/api/v1/entities", False),
    ],
)
def test_complete_template_json_allowance_has_an_exact_bounded_route(method, path, expanded):
    from app.modules.regulatory.request_limits import json_body_limit

    assert json_body_limit(path, method, 65536) == (8 * 1024 * 1024 if expanded else 65536)
