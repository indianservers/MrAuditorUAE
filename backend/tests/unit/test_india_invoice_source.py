import copy
import io
import json
import uuid
from decimal import Decimal

import pytest

from app.modules.audit_execution.evidence import validate_file
from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.native_sources import parse_native
from app.modules.country_workflows.schemas import SourceInput, TaxDocument, WorkflowInput
from tests.unit.test_country_workflows import parsed

SELLER = "29ABCDE1234F1Z5"
BUYER = "27ABCDE5678G1Z8"


def invoice(**changes):
    value = {
        "Version": "1.1",
        "TranDtls": {"TaxSch": "GST", "SupTyp": "B2B", "RegRev": "N"},
        "DocDtls": {"Typ": "INV", "No": "SYNTHETIC-1", "Dt": "15/06/2026"},
        "SellerDtls": {"Gstin": SELLER},
        "BuyerDtls": {"Gstin": BUYER},
        "ItemList": [{"SlNo": "1", "AssAmt": 100, "IgstAmt": 18, "TotItemVal": 118}],
        "ValDtls": {"AssVal": 100, "IgstVal": 18, "TotInvVal": 118},
    }
    value.update(changes)
    return value


def options(**changes):
    payload = dict(
        evidence_version_id=uuid.uuid4(),
        file_format="india-inv01-json",
        table_type="tax-documents",
        label="SYNTHETIC invoice source",
        expected_rows=5,
        control_totals={"INR": "18"},
        gst_registration=BUYER,
        gst_direction="purchase",
        gst_period="2026-06",
    )
    payload.update(changes)
    return SourceInput(**payload)


def parse(document, data=None, country="IN"):
    return parse_native(json.dumps(document).encode(), data or options(), country, "synthetic.json")


def test_invoice_controls_components_party_direction_and_status():
    result = parse(invoice())
    assert result["row_count"] == 5
    components = {row["component"]: row for row in result["rows"]}
    assert Decimal(components["IGST"]["tax"]) == 18
    assert sum(Decimal(row["tax"]) for row in result["rows"]) == 18
    assert all(
        row["registration"] == BUYER and row["counterparty"] == SELLER for row in result["rows"]
    )
    assert all(row["irp_authenticity"] == "NOT_VERIFIED" for row in result["rows"])
    assert result["native_metadata"]["document_controls"][0]["invoice_total"] == "118"
    assert result["review_status"] == "UNVERIFIED"
    assert (
        validate_file(io.BytesIO(json.dumps(invoice()).encode()), "invoice.json")
        == "application/json"
    )


@pytest.mark.parametrize("typ,sign", [("CRN", -1), ("DBN", 1)])
def test_credit_note_sign_and_debit_note(typ, sign):
    document = invoice()
    document["DocDtls"]["Typ"] = typ
    result = parse(document, options(control_totals={"INR": str(18 * sign)}))
    assert Decimal(result["rows"][0]["tax"]) == 18 * sign
    assert Decimal(result["rows"][0]["net"]) == 100 * sign


def test_sale_and_prior_period_invoice_keep_explicit_reporting_period():
    result = parse(
        invoice(), options(gst_registration=SELLER, gst_direction="sale", gst_period="2026-07")
    )
    assert result["rows"][0]["counterparty"] == BUYER
    assert result["rows"][0]["date"] == "2026-06-15"
    assert result["rows"][0]["period"] == "2026-07"


def test_cess_non_ad_valorem_reverse_charge_and_document_rounding_are_retained():
    document = invoice()
    document["TranDtls"]["RegRev"] = "Y"
    document["ItemList"][0].update(
        CesAmt=2, CesNonAdvlAmt=3, StateCesAmt=4, StateCesNonAdvlAmt=1, TotItemVal=128
    )
    document["ValDtls"].update(
        CesVal=5, StCesVal=5, Discount=6, OthChrg=2, RndOffAmt="-0.50", TotInvVal="123.50"
    )
    result = parse(document, options(control_totals={"INR": "28"}))
    taxes = {row["component"]: Decimal(row["tax"]) for row in result["rows"]}
    assert taxes == {
        "IGST": Decimal(18),
        "CGST": Decimal(0),
        "SGST": Decimal(0),
        "CESS": Decimal(5),
        "STATE_CESS": Decimal(5),
    }
    assert all(row["reverse_charge"] == "Y" for row in result["rows"])
    assert result["native_metadata"]["document_controls"][0]["invoice_total"] == "123.50"
    assert result["native_metadata"]["itc_eligibility"] == "NOT_DETERMINED"


def test_zero_tax_and_offsetting_credit_notes_are_not_nil_populations():
    document = invoice()
    document["ItemList"][0].update(IgstAmt=0, TotItemVal=100)
    document["ValDtls"].update(IgstVal=0, TotInvVal=100)
    result = parse(document, options(control_totals={"INR": "0"}))
    assert result["row_count"] == 5 and result["nil_reason"] is None
    credit = invoice()
    credit["DocDtls"]["Typ"] = "CRN"
    result = parse([invoice(), credit], options(expected_rows=10, control_totals={"INR": "0"}))
    assert result["row_count"] == 10
    assert result["native_metadata"]["document_count"] == 2


def test_negative_cess_cannot_be_hidden_by_positive_non_ad_valorem_cess():
    document = invoice()
    document["ItemList"][0].update(CesAmt=-5, CesNonAdvlAmt=5)
    with pytest.raises(ValueError, match="unsigned"):
        parse(document)


def test_future_reporting_period_cannot_reconcile_even_with_an_earlier_invoice_date():
    native = parse(invoice(), options(gst_period="2026-07"))
    sources = {"books": parsed("tax-documents", [{key: value for key, value in row.items() if key in TaxDocument.model_fields} for row in native["rows"]]), "invoices": native}
    data = WorkflowInput(
        workflow="india-invoice-register",
        invoice_direction="purchase",
        source_ids={role: uuid.uuid4() for role in sources},
        as_of="2026-06-30",
        currency="INR",
        title="Synthetic future return",
        rationale="Reporting month cannot precede the reconciliation cutoff",
    )
    with pytest.raises(ValueError, match="reporting period is after"):
        calculate(data, "IN", sources)


@pytest.mark.parametrize("defect", [None, "tax", "net", "date", "period", "status", "reference"])
@pytest.mark.parametrize("native_role", ["books", "invoices"])
def test_native_components_compare_with_sparse_purchase_register_without_hiding_exceptions(
    defect, native_role
):
    native = parse(invoice())
    row = {
        key: value
        for key, value in native["rows"][0].items()
        if key
        in {
            "id",
            "registration",
            "counterparty",
            "reference",
            "period",
            "date",
            "currency",
            "document_type",
            "net",
            "tax",
            "component",
            "status",
        }
    }
    changes = {
        "tax": "17",
        "net": "99",
        "date": "2026-06-14",
        "period": "2026-05",
        "status": "pending",
        "reference": "OTHER",
    }
    if defect:
        row[defect] = changes[defect]
    other_role = "return" if native_role == "books" else "books"
    sources = {native_role: native, other_role: parsed("tax-documents", [row])}
    data = WorkflowInput(
        workflow="india-gst" if native_role == "books" else "india-invoice-register",
        **({"invoice_direction": "purchase"} if native_role == "invoices" else {}),
        source_ids={role: uuid.uuid4() for role in sources},
        as_of="2026-06-30",
        currency="INR",
        title="Synthetic native invoice bridge",
        rationale="Independent sparse register and native invoice controls",
    )
    result = calculate(data, "IN", sources)
    if defect:
        assert result["exception_count"] > 0
    else:
        assert result["exception_count"] == 0
        assert (
            sum(
                row["comparison_basis"]
                == "EXPLICIT_NATIVE_ZERO_COMPONENT_WITH_OPPOSITE_DOCUMENT_PRESENT"
                for row in result["rows"]
            )
            == 4
        )


@pytest.mark.parametrize(
    "path,value",
    [
        (("Version",), "1.0"),
        (("DocDtls", "Dt"), "2026-06-15"),
        (("DocDtls", "Typ"), "OTHER"),
        (("DocDtls", "No"), "bad invoice"),
        (("BuyerDtls", "Gstin"), SELLER),
        (("TranDtls", "SupTyp"), "EXPWP"),
        (("TranDtls", "RegRev"), "?"),
        (("ValDtls", "AssVal"), 101),
        (("ValDtls", "IgstVal"), 19),
        (("ValDtls", "TotInvVal"), 119),
        (("ItemList",), []),
        (("SignedInvoice",), "not-authenticated"),
    ],
)
def test_invalid_documents_fail_closed(path, value):
    document = invoice()
    target = document
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        parse(document)


def test_duplicate_documents_items_future_dates_and_country_boundary():
    with pytest.raises(ValueError, match="Duplicate"):
        parse([invoice(), invoice()], options(expected_rows=10, control_totals={"INR": "36"}))
    document = invoice()
    document["ItemList"].append(copy.deepcopy(document["ItemList"][0]))
    with pytest.raises(ValueError, match="serials"):
        parse(document)
    with pytest.raises(ValueError, match="after"):
        parse(invoice(), options(gst_period="2026-05"))
    with pytest.raises(ValueError, match="country"):
        parse(invoice(), country="AE")
    with pytest.raises(ValueError, match="row-count"):
        parse(invoice(), options(expected_rows=1))
    with pytest.raises(ValueError, match="currency control"):
        parse(invoice(), options(control_totals={"INR": "19"}))


@pytest.mark.parametrize(
    "content", [b'{"a":1,"a":2}', b'{"tax":NaN}', b'{"tax":Infinity}', b"{", b'"text"', b"[\x00]"]
)
def test_unsafe_json_evidence_rejected(content):
    with pytest.raises(ValueError):
        validate_file(io.BytesIO(content), "invoice.json")


def test_native_invoice_is_not_filed_return_evidence_even_when_amounts_agree():
    native = parse(invoice())
    register = parsed("tax-documents", [{key: value for key, value in row.items() if key in TaxDocument.model_fields} for row in native["rows"]])
    data = WorkflowInput(workflow="india-gst",source_ids={"books":uuid.uuid4(),"return":uuid.uuid4()},as_of="2026-06-30",currency="INR",title="SYNTHETIC wrong evidence role",rationale="Identical invoice amounts cannot establish a filed return")
    with pytest.raises(ValueError, match="not a filed GST return"):
        calculate(data,"IN",{"books":register,"return":native})


@pytest.mark.parametrize("direction", ["purchase", "sale"])
def test_explicit_invoice_direction_and_invoice_labels_are_preserved(direction):
    native = parse(invoice(), options(gst_direction=direction,gst_registration=BUYER if direction=="purchase" else SELLER))
    register = parsed("tax-documents", [{key:value for key,value in row.items() if key in TaxDocument.model_fields} for row in native["rows"]])
    data = WorkflowInput(workflow="india-invoice-register",invoice_direction=direction,source_ids={"books":uuid.uuid4(),"invoices":uuid.uuid4()},as_of="2026-06-30",currency="INR",title="SYNTHETIC invoice register",rationale="Independent register compared with retained invoice evidence")
    result=calculate(data,"IN",{"books":register,"invoices":native})
    assert result["exception_count"]==0
    assert result["invoice_evidence_scope"]["direction"]==direction
    assert result["invoice_evidence_scope"]["filing_status"]=="NOT_ASSESSED_BY_INVOICE_COMPARISON"
    assert "invoices_tax" in result["rows"][0] and "return_tax" not in result["rows"][0]
    with pytest.raises(ValueError,match="direction differs"):
        calculate(data.model_copy(update={"invoice_direction":"sale" if direction=="purchase" else "purchase"}),"IN",{"books":register,"invoices":native})
    with pytest.raises(ValueError,match="not a filed GST return"):
        calculate(data,"IN",{"books":native,"invoices":register})


def test_sale_invoice_cannot_clear_an_inward_gstr2b_document_with_matching_identifiers():
    native = parse(invoice(),options(gst_direction="sale",gst_registration=SELLER))
    inward = parsed("tax-documents", [{key:value for key,value in row.items() if key in TaxDocument.model_fields} for row in native["rows"]])
    inward["native_format"]="india-gstr2b-json"
    data=WorkflowInput(workflow="india-gst",source_ids={"books":uuid.uuid4(),"return":uuid.uuid4()},as_of="2026-06-30",currency="INR",title="SYNTHETIC dual-role counterparty",rationale="A customer may also be a supplier; matching IDs do not erase direction")
    with pytest.raises(ValueError,match="sales invoice cannot establish purchase books"):
        calculate(data,"IN",{"books":native,"return":inward})
