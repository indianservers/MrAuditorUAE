import copy
import json
import uuid

import pytest

from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.native_sources import parse_native
from app.modules.country_workflows.schemas import SourceInput, WorkflowInput

GSTIN = "27ABCDE5678G1Z8"
PARTY = "29ABCDE1234F1Z5"


def invoice(reference="SYN-REG1", base=100, tax=18, amend=False):
    result = {
        "inum": reference,
        "idt": "15-06-2026",
        "val": base + tax,
        "chksum": "SYNTHETIC-not-authenticated",
        "inv_typ": "R",
        "rchrg": "N",
        "pos": "07",
        "updby": "S",
        "cflag": "N",
        "itms": [{"num": 1, "itm_det": {"rt": 18, "txval": base, "iamt": tax}}],
    }
    if amend:
        result.update(oinum="SYN-REG1", oidt="15-05-2026")
    return result


def note(reference, base, tax, kind="C", amend=False):
    result = invoice(reference, base, tax)
    result["nt_num"] = result.pop("inum")
    result["nt_dt"] = result.pop("idt")
    result["ntty"] = kind
    result["flag"] = "N"
    if amend:
        result.update(ont_num="OLD-NOTE", ont_dt="15-05-2026")
    return result


def all_sections():
    result = {
        "b2b": [{"ctin": PARTY, "cfs": "N", "inv": [invoice()]}],
        "b2ba": [{"ctin": PARTY, "inv": [invoice(base=120, tax=21.6, amend=True)]}],
        "b2cl": [{"pos": "07", "inv": [invoice("B2CL-1")]}],
        "b2cla": [{"pos": "07", "inv": [invoice("B2CLA-1", 120, 21.6, True)]}],
        "cdnr": [{"ctin": PARTY, "nt": [note("CREDIT-1", 50, 9)]}],
        "cdnra": [{"ctin": PARTY, "nt": [note("DEBIT-1", 40, 7.2, "D", True)]}],
        "cdnur": [{**note("UR-CREDIT", 20, 3.6), "typ": "B2CL"}],
        "cdnura": [{**note("UR-DEBIT", 30, 5.4, "D", True), "typ": "EXPWP"}],
        "exp": [{"exp_typ": "WPAY", "inv": [invoice("EXPORT-1")]}],
        "expa": [{"exp_typ": "WOPAY", "inv": [invoice("EXPORT-OLD", 100, 0, True)]}],
    }
    for section in ("b2cl", "b2cla"):
        for doc in result[section][0]["inv"]:
            for key in ("inv_typ", "rchrg", "pos", "updby", "cflag"):
                doc.pop(key, None)
            if section == "b2cla":
                doc["flag"] = "N"
    for section in ("cdnur", "cdnura"):
        for doc in result[section]:
            for key in ("inv_typ", "rchrg", "updby", "cflag"):
                doc.pop(key, None)
    for section in ("exp", "expa"):
        for doc in result[section][0]["inv"]:
            for key in ("inv_typ", "rchrg", "pos", "updby", "cflag"):
                doc.pop(key, None)
            doc["flag"] = "N"
            doc["itms"] = [{"rt": 18, "txval": 100, "iamt": 18 if section == "exp" else 0}]
    return result


def controls(all=False):
    values = [("b2b", 100, "18")]
    if all:
        values += [
            ("b2ba", 120, "21.6"),
            ("b2cl", 100, "18"),
            ("b2cla", 120, "21.6"),
            ("cdnr", -50, "-9"),
            ("cdnra", 40, "7.2"),
            ("cdnur", -20, "-3.6"),
            ("cdnura", 30, "5.4"),
            ("exp", 100, "18"),
            ("expa", 100, "0"),
        ]
    return [
        {
            "section": section,
            "document_count": 1,
            "taxable_base": str(base),
            "igst": tax,
            "cgst": "0",
            "sgst": "0",
            "cess": "0",
        }
        for section, base, tax in values
    ]


def options(all=False, **changes):
    args = dict(
        evidence_version_id=uuid.uuid4(),
        file_format="india-gstr1-documents-json",
        table_type="tax-documents",
        label="SYNTHETIC outward invoices",
        gst_registration=GSTIN,
        gst_period="2026-06",
        expected_documents=10 if all else 1,
        expected_rows=40 if all else 4,
        control_totals={"INR": "97.2" if all else "18"},
        gstr1_section_controls=controls(all),
        gstr1_context_evidence_version_id=uuid.uuid4(),
        gstr1_retrieval_assessment="Independent synthetic request GSTIN, month, sections and filtering/pagination assessed; no filing conclusion",
    )
    args.update(changes)
    return SourceInput(**args)


def parsed(payload=None, all=False, **changes):
    if payload is None:
        payload = all_sections() if all else {"b2b": all_sections()["b2b"]}
    return parse_native(json.dumps(payload).encode(), options(all, **changes), "IN", "gstr1.json")


def books():
    return {
        "table_type": "tax-documents",
        "control_totals": {"INR": "18"},
        "rows": [
            {
                "id": "BOOK-" + head,
                "registration": GSTIN,
                "counterparty": PARTY,
                "reference": "SYN-REG1",
                "period": "2026-06",
                "date": "2026-06-15",
                "currency": "INR",
                "document_type": "invoice",
                "net": "100",
                "tax": "18" if head == "IGST" else "0",
                "component": head,
                "status": "active",
            }
            for head in ("IGST", "CGST", "SGST", "CESS")
        ],
    }


def workflow(**changes):
    args = dict(
        workflow="india-gstr1-documents",
        source_ids={"books": uuid.uuid4(), "return": uuid.uuid4()},
        as_of="2026-06-30",
        currency="INR",
        title="SYNTHETIC outward review",
        rationale="Independent source registers, original response and retained request context",
    )
    args.update(changes)
    return WorkflowInput(**args)


def test_all_ten_sections_keep_notes_categories_amendments_and_components():
    result = parsed(all=True)
    assert result["row_count"] == 40
    assert result["control_totals"] == {"INR": "97.2"}
    assert result["allowed_source_roles"] == ["return"]
    assert result["native_metadata"]["document_count"] == 10
    assert result["native_metadata"]["filing_status"] == "NOT_ESTABLISHED_BY_DOCUMENT_RESPONSE"
    assert (
        next(
            r for r in result["rows"] if r["source_section"] == "cdnr" and r["component"] == "IGST"
        )["tax"]
        == "-9"
    )
    assert (
        next(r for r in result["rows"] if r["source_section"] == "cdnura")["counterparty"]
        == "EXPORT:WPAY"
    )
    assert all(
        r["original_reference"] and r["source_review_reasons"]
        for r in result["rows"]
        if r["source_section"].endswith("a")
    )
    pending = calculate(workflow(), "IN", {"books": books(), "return": result})
    assert all(
        r["state"] == "SOURCE_DOCUMENT_REVIEW_REQUIRED"
        for r in pending["rows"]
        if r.get("return_source_section") == "b2ba"
    )


def test_independent_sales_books_match_native_return_and_wrappers_preserve_exactness():
    result = parsed()
    matched = calculate(workflow(), "IN", {"books": books(), "return": result})
    assert matched["exception_count"] == 0
    assert len(matched["rows"]) == 4
    wrapped = {"code": 200, "data": {"status_cd": "1", "data": {"b2b": all_sections()["b2b"]}}}
    assert parsed(wrapped)["native_metadata"]["transparent_wrapper_depth"] == 2
    changed = copy.deepcopy(books())
    changed["rows"][0]["tax"] = "17"
    assert calculate(workflow(), "IN", {"books": changed, "return": result})["exception_count"] == 1


@pytest.mark.parametrize(
    "defect",
    [
        "unknown_section",
        "unknown_field",
        "duplicate_doc",
        "duplicate_item",
        "negative_amount",
        "boolean_amount",
        "wrong_date",
        "missing_amendment",
        "missing_pos",
        "head_swap",
        "base_control",
        "section_count",
        "unsuccessful_wrapper",
        "delink_flag",
        "gross_difference",
    ],
)
def test_document_boundaries_and_source_review_flags(defect):
    payload = {"b2b": all_sections()["b2b"]}
    data = {}
    doc = payload["b2b"][0]["inv"][0]
    if defect == "unknown_section":
        payload["b2cs"] = []
    elif defect == "unknown_field":
        doc["future_amount"] = 0
    elif defect == "duplicate_doc":
        payload["b2b"][0]["inv"].append(copy.deepcopy(doc))
    elif defect == "duplicate_item":
        doc["itms"] *= 2
    elif defect == "negative_amount":
        doc["itms"][0]["itm_det"]["iamt"] = -18
    elif defect == "boolean_amount":
        doc["val"] = True
    elif defect == "wrong_date":
        doc["idt"] = "01-07-2026"
    elif defect == "missing_amendment":
        payload = {"b2ba": [{"ctin": PARTY, "inv": [doc]}]}
        data["gstr1_section_controls"] = [{**controls()[0], "section": "b2ba"}]
    elif defect == "missing_pos":
        payload = {"b2cl": [{"inv": [doc]}]}
        data["gstr1_section_controls"] = [{**controls()[0], "section": "b2cl"}]
    elif defect == "head_swap":
        doc["itms"][0]["itm_det"].update(iamt=0, camt=18)
    elif defect == "base_control":
        data["gstr1_section_controls"] = [{**controls()[0], "taxable_base": "99"}]
    elif defect == "section_count":
        data.update(
            expected_documents=2,
            expected_rows=8,
            gstr1_section_controls=[{**controls()[0], "document_count": 2}],
        )
    elif defect == "unsuccessful_wrapper":
        payload = {"code": 400, "data": payload}
    elif defect == "delink_flag":
        payload = {"cdnr": all_sections()["cdnr"]}
        payload["cdnr"][0]["nt"][0]["d_flag"] = "Y"
        data.update(
            control_totals={"INR": "-9"},
            gstr1_section_controls=[
                {
                    "section": "cdnr",
                    "document_count": 1,
                    "taxable_base": "-50",
                    "igst": "-9",
                    "cgst": "0",
                    "sgst": "0",
                    "cess": "0",
                }
            ],
        )
    elif defect == "gross_difference":
        doc["val"] = 119
    if defect in {"delink_flag", "gross_difference"}:
        result = parsed(payload, **data)
        assert all(r["source_review_reasons"] for r in result["rows"])
        assert calculate(workflow(), "IN", {"books": books(), "return": result})["blocked"]
    else:
        with pytest.raises(ValueError):
            parsed(payload, **data)


def test_context_controls_country_and_role_substitution_are_not_optional():
    with pytest.raises(ValueError):
        options(gstr1_context_evidence_version_id=None)
    with pytest.raises(ValueError):
        options(gstr1_retrieval_assessment="")
    with pytest.raises(ValueError):
        options(gstr1_section_controls=[controls()[0], controls()[0]])
    result = parsed()
    with pytest.raises(ValueError, match="unavailable"):
        calculate(workflow(), "AE", {"books": books(), "return": result})
    with pytest.raises(ValueError, match="only the outward"):
        calculate(workflow(), "IN", {"books": result, "return": books()})
    with pytest.raises(ValueError, match="requires INR"):
        calculate(workflow(currency="AED"), "IN", {"books": books(), "return": result})


def test_multiple_rate_items_are_aggregated_once_with_original_records_retained():
    payload = {"b2b": all_sections()["b2b"]}
    payload["b2b"][0]["inv"][0]["itms"] = [
        {"num": 1, "itm_det": {"rt": 18, "txval": 60, "iamt": 10.8}},
        {"num": 2, "itm_det": {"rt": 18, "txval": 40, "iamt": 7.2}},
    ]
    result = parsed(payload)
    assert result["row_count"] == 4
    assert result["native_metadata"]["rate_item_count"] == 2
    assert len(result["native_metadata"]["original_rate_records"][0]["rate_items"]) == 2
    assert calculate(workflow(), "IN", {"books": books(), "return": result})["exception_count"] == 0


def test_native_sales_evidence_cannot_be_substituted_by_an_identical_purchase():
    from tests.unit.test_india_invoice_source import invoice as inv01
    from tests.unit.test_india_invoice_source import options as inv_options

    document = inv01()
    document["DocDtls"]["No"] = "SYN-REG1"
    purchase = parse_native(json.dumps(document).encode(), inv_options(), "IN", "inv.json")
    with pytest.raises(ValueError, match="sales invoice evidence"):
        calculate(workflow(), "IN", {"books": purchase, "return": parsed()})
    document["SellerDtls"]["Gstin"], document["BuyerDtls"]["Gstin"] = GSTIN, PARTY
    sale = parse_native(
        json.dumps(document).encode(),
        inv_options(gst_direction="sale", gst_registration=GSTIN),
        "IN",
        "inv.json",
    )
    assert calculate(workflow(), "IN", {"books": sale, "return": parsed()})["exception_count"] == 0
    with pytest.raises(ValueError, match="reporting month extends"):
        calculate(workflow(as_of="2026-06-20"), "IN", {"books": books(), "return": parsed()})


def test_controlled_empty_section_does_not_claim_a_nil_full_return():
    result = parsed(
        {"b2b": []},
        expected_documents=0,
        expected_rows=0,
        nil_reason="Independently assessed empty retained B2B section only",
        control_totals={"INR": "0"},
        gstr1_section_controls=[
            {
                "section": "b2b",
                "document_count": 0,
                "taxable_base": "0",
                "igst": "0",
                "cgst": "0",
                "sgst": "0",
                "cess": "0",
            }
        ],
    )
    assert result["row_count"] == 0
    assert result["native_metadata"]["source_population_scope"].endswith(
        "NOT_COMPLETE_GSTR1_RETURN"
    )
    assert result["native_metadata"]["filing_status"] == "NOT_ESTABLISHED_BY_DOCUMENT_RESPONSE"


def test_document_bound_is_enforced_across_groups():
    payload = {
        "b2b": [
            {"ctin": PARTY, "inv": [invoice(f"BOUND-{i}") for i in range(625)]},
            {"ctin": PARTY, "inv": [invoice(f"BOUND-{i}") for i in range(625, 1251)]},
        ]
    }
    with pytest.raises(ValueError, match="1,250"):
        parsed(
            payload,
            expected_documents=1250,
            expected_rows=5000,
            control_totals={"INR": "22500"},
            gstr1_section_controls=[
                {
                    "section": "b2b",
                    "document_count": 1250,
                    "taxable_base": "125000",
                    "igst": "22500",
                    "cgst": "0",
                    "sgst": "0",
                    "cess": "0",
                }
            ],
        )
