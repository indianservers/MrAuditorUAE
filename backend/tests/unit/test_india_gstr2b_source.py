import copy
import json
import uuid
from decimal import Decimal

import pytest

from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.native_sources import parse_native
from app.modules.country_workflows.schemas import SourceInput, TaxDocument, WorkflowInput
from tests.unit.test_country_workflows import parsed
from tests.unit.test_india_invoice_source import BUYER, SELLER


def document(**changes):
    return {
        "inum": "SYNTHETIC-1",
        "typ": "R",
        "dt": "15-06-2026",
        "val": 118,
        "txval": 100,
        "igst": 18,
        "cgst": 0,
        "sgst": 0,
        "cess": 0,
        "itcavl": "Y",
        "rev": "N",
        "imsStatus": "N",
        **changes,
    }


def payload():
    return {
        "gstin": BUYER,
        "rtnprd": "062026",
        "version": "1.0",
        "gendt": "14-07-2026",
        "docdata": {"b2b": [{"ctin": SELLER, "supprd": "062026", "inv": [document()]}]},
        "cpsumm": {"b2b": [{"ctin": SELLER, "supprd": "062026", "ttldocs": 1}]},
    }


def options(**changes):
    values = dict(
        evidence_version_id=uuid.uuid4(),
        file_format="india-gstr2b-json",
        table_type="tax-documents",
        label="SYNTHETIC GSTR-2B document profile",
        expected_rows=4,
        expected_documents=1,
        control_totals={"INR": "18"},
        gst_registration=BUYER,
        gst_period="2026-06",
    )
    values.update(changes)
    return SourceInput(**values)


def parse(value=None, data=None, country="IN"):
    return parse_native(
        json.dumps(value if value is not None else payload()).encode(),
        data or options(),
        country,
        "synthetic-gstr2b.json",
    )


def compare(source):
    books = [
        {key: value for key, value in row.items() if key in TaxDocument.model_fields}
        for row in source["rows"]
    ]
    sources = {"books": parsed("tax-documents", books), "return": source}
    request = WorkflowInput(
        workflow="india-gst",
        source_ids={role: uuid.uuid4() for role in sources},
        as_of="2026-06-30",
        currency="INR",
        title="Synthetic GSTR-2B comparison",
        rationale="Explicit source document profile and separately prepared book schedule",
    )
    return calculate(request, "IN", sources)


def test_invoice_totals_rows_controls_and_reconciliation():
    result = parse()
    assert result["row_count"] == 4
    assert result["native_metadata"]["document_count"] == 1
    assert result["native_metadata"]["amount_layout_counts"] == {"invoice-totals": 1}
    assert Decimal(result["control_totals"]["INR"]) == 18
    assert {row["component"] for row in result["rows"]} == {"IGST", "CGST", "SGST", "CESS"}
    assert compare(result)["exception_count"] == 0
    assert result["statutory_calculation_qualified"] is False


def test_item_sums_and_optional_aggregate_cross_controls():
    value = payload()
    invoice = value["docdata"]["b2b"][0]["inv"][0]
    invoice["items"] = [
        {"num": 1, "txval": 40, "igst": "7.2"},
        {"num": 2, "txval": 60, "igst": "10.8"},
    ]
    result = parse(value)
    assert result["native_metadata"]["amount_layout_counts"] == {"item-sums": 1}
    assert Decimal(result["rows"][0]["tax"]) == 18
    invoice["igst"] = 19
    with pytest.raises(ValueError, match="item totals differ"):
        parse(value)


@pytest.mark.parametrize(
    "wrapper",
    [
        lambda value: {"chksum": "unverified-source-checksum", "data": value},
        lambda value: {
            "code": 200,
            "data": {"status_cd": "1", "data": {"chksum": "unverified", "data": value}},
        },
    ],
)
def test_transparent_document_and_success_provider_wrappers(wrapper):
    result = parse(wrapper(payload()))
    assert result["native_metadata"]["transparent_wrapper_depth"] in {1, 3}
    assert result["native_metadata"]["provider_authenticity"] == "NOT_VERIFIED"
    assert result["native_metadata"]["wrapper_checksums"]


@pytest.mark.parametrize("section", ["b2ba", "cdnr", "cdnra", "ecom", "ecoma"])
def test_notes_and_amendments_preserve_signed_direction_and_review(section):
    value = payload()
    invoice = document()
    supplier = {"ctin": SELLER, "supprd": "062026"}
    if section.startswith("cdn"):
        invoice["ntnum"] = invoice.pop("inum")
        invoice["typ"] = "C"
        invoice.update(ontnum="ORIGINAL-1", ontdt="01-05-2026", onttyp="C")
        supplier["nt"] = [invoice]
    else:
        invoice.update(oinum="ORIGINAL-1", oidt="01-05-2026")
        supplier["inv"] = [invoice]
    value["docdata"], value["cpsumm"] = {section: [supplier]}, {}
    negative = section.startswith("cdn")
    result = parse(value, options(control_totals={"INR": "-18" if negative else "18"}))
    assert Decimal(result["rows"][0]["tax"]) == (-18 if negative else 18)
    assert result["rows"][0]["document_type"] == ("credit-note" if negative else "invoice")
    if section in {"b2ba", "cdnra", "ecoma"}:
        assert all(row["source_review_reasons"] for row in result["rows"])
        assert compare(result)["exception_count"] == 4


@pytest.mark.parametrize(
    "section,typ,total", [("isd", "ISDI", "18"), ("isd", "ISDC", "-18"), ("isda", "ISDI", "18")]
)
def test_isd_allocation_never_invents_a_verified_zero_taxable_base(section, typ, total):
    value = payload()
    allocation = {
        "doctyp": typ,
        "docnum": "ALLOC-1",
        "docdt": "15-06-2026",
        "cgst": 9,
        "sgst": 9,
        "itcelg": "Y",
    }
    value["docdata"], value["cpsumm"] = {section: [{"ctin": SELLER, "doclist": [allocation]}]}, {}
    result = parse(value, options(control_totals={"INR": total}))
    assert all(row["net_available"] is False for row in result["rows"])
    compared = compare(result)
    assert all(
        row["state"] == "SOURCE_DOCUMENT_REVIEW_REQUIRED" and row["net_difference"] is None
        for row in compared["rows"]
    )


@pytest.mark.parametrize("section", ["impg", "impgsez"])
def test_bills_of_entry_use_port_and_boe_reference_without_inventing_supplier_identity(section):
    value = payload()
    entry = {
        "portcode": "INBOM4",
        "boenum": "1234567",
        "boedt": "15-06-2026",
        "isamd": "N",
        "txval": 100,
        "igst": 18,
        "cess": 0,
    }
    value["docdata"] = {
        section: [entry] if section == "impg" else [{"ctin": SELLER, "boe": [entry]}]
    }
    value["cpsumm"] = {}
    result = parse(value)
    assert all(
        row["counterparty"] == "CUSTOMS:INBOM4" and row["reference"] == "1234567"
        for row in result["rows"]
    )
    assert compare(result)["exception_count"] == 0


def test_credit_reversal_is_separate_and_not_silently_netted_against_credit():
    value = payload()
    value["docdata"] = {"itcrev": [{"b2b": value["docdata"]["b2b"]}]}
    value["cpsumm"] = {}
    result = parse(value)
    assert result["native_metadata"]["section_document_counts"] == {"itcrev/b2b": 1}
    assert Decimal(result["rows"][0]["tax"]) == 18
    assert compare(result)["exception_count"] == 4


@pytest.mark.parametrize(
    "change", [{"itcavl": "N"}, {"imsStatus": "R"}, {"imsStatus": "P"}, {"imsStatus": "UNKNOWN"}]
)
def test_credit_and_ims_status_cannot_be_hidden_by_matching_amounts(change):
    value = payload()
    value["docdata"]["b2b"][0]["inv"][0].update(change)
    assert compare(parse(value))["exception_count"] == 4


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update(version="2.0"),
        lambda value: value.update(gstin=SELLER),
        lambda value: value.update(rtnprd="072026"),
        lambda value: value["cpsumm"]["b2b"][0].update(ttldocs=2),
        lambda value: value["docdata"].update(unknown_section=[]),
        lambda value: value["docdata"]["b2b"][0]["inv"].append(
            copy.deepcopy(value["docdata"]["b2b"][0]["inv"][0])
        ),
        lambda value: value["docdata"]["b2b"][0]["inv"][0].update(igst=-18),
        lambda value: value["docdata"]["b2b"][0]["inv"][0].update(dt="01-07-2026"),
    ],
)
def test_scope_malformed_and_population_controls_fail_closed(mutate):
    value = payload()
    mutate(value)
    with pytest.raises(ValueError):
        parse(value)


@pytest.mark.parametrize(
    "wrapped",
    [
        {"code": 500, "data": payload()},
        {"code": 200, "data": {"status_cd": "0", "error": {"error_cd": "NO_DATA"}}},
        {"code": 200, "data": {"status_cd": "3", "data": {"fc": 2}}},
        {"next_token": "second-page", "data": payload()},
    ],
)
def test_business_failure_and_partial_download_are_not_zero_activity(wrapped):
    with pytest.raises(ValueError):
        parse(wrapped)


def test_nil_source_requires_nil_reason_zero_summaries_and_count_controls():
    value = payload()
    value["docdata"], value["cpsumm"] = {}, {}
    data = options(
        expected_rows=0,
        expected_documents=0,
        control_totals={"INR": "0"},
        nil_reason="Synthetic independently evidenced nil document population",
    )
    assert parse(value, data)["row_count"] == 0
    value["itcsumm"] = {"itcavl": {"igst": 1}}
    with pytest.raises(ValueError, match="summaries contain"):
        parse(value, data)


def test_independent_counts_currency_and_country_boundaries():
    for changes in (
        {"expected_documents": 2},
        {"expected_rows": 1},
        {"control_totals": {"INR": "19"}},
        {"expected_documents": None},
    ):
        with pytest.raises(ValueError):
            parse(data=options(**changes))
    with pytest.raises(ValueError, match="country"):
        parse(country="AE")


def test_original_and_amended_versions_are_not_selected_or_summed_as_current_credit():
    value = payload()
    revised = document(oinum="SYNTHETIC-1", oidt="15-06-2026", txval=200, igst=36, val=236)
    value["docdata"]["b2ba"] = [{"ctin": SELLER, "supprd": "062026", "inv": [revised]}]
    source = parse(
        value, options(expected_rows=8, expected_documents=2, control_totals={"INR": "54"})
    )
    book_row = {
        key: val for key, val in source["rows"][0].items() if key in TaxDocument.model_fields
    }
    populations = {"books": parsed("tax-documents", [book_row]), "return": source}
    request = WorkflowInput(
        workflow="india-gst",
        source_ids={role: uuid.uuid4() for role in populations},
        as_of="2026-06-30",
        currency="INR",
        title="Synthetic amendment version review",
        rationale="Keep original and revised source records separately for assessment",
    )
    result = calculate(request, "IN", populations)
    assert result["exception_count"] == 4
    for row in result["rows"]:
        assert row["state"] == "SOURCE_DOCUMENT_REVIEW_REQUIRED"
        assert row["return_tax"] is None and row["tax_difference"] is None
        assert len(row["return_version_source_ids"]) == 2
        assert "MULTIPLE_SOURCE_VERSIONS_REQUIRE_RESOLUTION" in row["source_review_reasons"]
    igst = next(row for row in result["rows"] if row["component"] == "IGST")
    assert {Decimal(version["tax"]) for version in igst["return_source_versions"]} == {
        Decimal(18),
        Decimal(36),
    }


def test_native_decimal_exponents_are_bounded_and_do_not_round_through_binary_float():
    value = payload()
    value["docdata"]["b2b"][0]["inv"][0].update(igst=0.00000001)
    result = parse(value, options(control_totals={"INR": "0.00000001"}))
    assert Decimal(result["rows"][0]["tax"]) == Decimal("0.00000001")
    with pytest.raises(ValueError):
        parse_native(
            json.dumps(payload()).replace('"igst": 18', '"igst": 1e99999').encode(),
            options(),
            "IN",
            "bad.json",
        )


def test_customs_gstin_and_declared_credit_changes_remain_separate_from_original_tax():
    value = payload()
    entry = {
        "portcode": "INBOM4",
        "boenum": "1234567",
        "boedt": "15-06-2026",
        "isamd": "Y",
        "txval": 100,
        "igst": 18,
        "cess": 0,
        "amendType": "G",
        "itcRedReq": "Y",
        "declIgst": 10,
        "declCess": 0,
        "isReversal": "Y",
    }
    value["docdata"], value["cpsumm"] = {"impg": [entry]}, {}
    result = parse(value)
    assert result["rows"][0]["source_declared_igst"] == "10"
    assert Decimal(result["rows"][0]["tax"]) == 18
    assert compare(result)["exception_count"] == 4


def test_malformed_history_fields_are_not_copied_as_unbounded_source_metadata():
    value = payload()
    value["docdata"]["b2b"][0]["inv"][0]["oinum"] = {"unexpected": "nested object"}
    with pytest.raises(ValueError):
        parse(value)
