"""Synthetic malformed instructions must not become valid through field trimming."""

import pytest

from app.modules.country_workflows.native_sources import parse_native
from tests.unit.native_source_examples import SIF, SIF_FILENAME
from tests.unit.test_native_workflow_sources import options


@pytest.mark.parametrize(
    "old,new",
    [
        (b"1000.00,", b'"1000.00\n",'),
        (b"1234567890123,", b'"1234567890123\n",'),
        (b"AED,SYNTHETIC\n", b'AED,"SYNTHETIC\nignored"\n'),
        (b"AED,SYNTHETIC\n", b'AED,"SYNTHETIC\n'),
        (b"1000.00,", b'"1000.00" ,'),
    ],
    ids=[
        "salary-newline",
        "employer-newline",
        "reference-newline",
        "unclosed-quote",
        "closing-quote-junk",
    ],
)
@pytest.mark.parametrize("profile", ["uae-wps-sif", "uae-wps-sif-evp"])
def test_wps_rejects_embedded_record_boundaries_and_malformed_csv(old, new, profile):
    from tests.unit.test_wps_variable_pay import SIF_EVP
    from tests.unit.test_wps_variable_pay import options as evp_options

    assert old in SIF
    with pytest.raises(ValueError):
        parse_native(
            (SIF if profile == "uae-wps-sif" else SIF_EVP).replace(old, new),
            options(profile) if profile == "uae-wps-sif" else evp_options(),
            "AE",
            SIF_FILENAME,
        )


@pytest.mark.parametrize("ending", [b"\n", b"\r\n", b"\r"])
def test_wps_keeps_normal_record_endings_and_quoted_single_line_fields(ending):
    content = SIF.replace(b"1000.00,", b'"1000.00",').replace(b"\n", ending)
    result = parse_native(content, options("uae-wps-sif"), "AE", SIF_FILENAME)
    assert result["row_count"] == 2 and result["control_totals"] == {"AED": "1500.00"}
    assert result["native_metadata"]["physical_record_count"] == 3
    assert result["native_metadata"]["record_boundary_contract"] == "wps-single-line-records/1"


@pytest.mark.parametrize(
    "metadata", [None, {}, {"record_boundary_contract": None}, {"record_boundary_contract": "old"}]
)
async def test_older_wps_sources_are_stale_before_any_dependency_is_traversed(metadata):
    from types import SimpleNamespace

    from app.modules.intelligence.service import current

    event = SimpleNamespace(
        tenant_id="tenant",
        kind="workflow-source",
        body={"native_format": "uae-wps-sif", "native_metadata": metadata},
    )
    assert await current(None, SimpleNamespace(tenant_id="tenant"), event) is False


def test_evp_profile_retains_its_original_physical_record_count_and_contract():
    from tests.unit.test_wps_variable_pay import parse

    metadata = parse()["native_metadata"]
    assert metadata["physical_record_count"] == 4
    assert metadata["record_boundary_contract"] == "wps-single-line-records/1"
