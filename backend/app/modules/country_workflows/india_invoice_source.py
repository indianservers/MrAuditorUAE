"""INV-01 1.1 document reader; no IRP authenticity or credit-eligibility assertion."""

import re
from datetime import datetime
from decimal import Decimal

from app.core.json_documents import read_json_document
from app.modules.country_workflows.schemas import TaxDocument

COMPONENTS = {
    "IGST": ("IgstAmt", "IgstVal"),
    "CGST": ("CgstAmt", "CgstVal"),
    "SGST": ("SgstAmt", "SgstVal"),
    "CESS": ("CesAmt", "CesVal"),
    "STATE_CESS": ("StateCesAmt", "StCesVal"),
}
GSTIN = r"\d{2}[A-Z]{5}\d{4}[A-Z][A-Z0-9]Z[A-Z0-9]"


def money(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError("Invalid e-invoice monetary value")
    if isinstance(value, Decimal):
        exponent = value.as_tuple().exponent
        if (
            not value.is_finite()
            or not isinstance(exponent, int)
            or not -8 <= exponent <= 20
            or value.copy_abs() >= Decimal("1e20")
        ):
            raise ValueError("Invalid e-invoice monetary value")
        value = format(value, "f")
    if not re.fullmatch(r"-?\d{1,20}(?:\.\d{1,8})?", str(value)):
        raise ValueError("Invalid e-invoice monetary value")
    return Decimal(value)


def gstin(value):
    if not isinstance(value, str) or not re.fullmatch(GSTIN, value):
        raise ValueError("A registered-party GSTIN is required for this import profile")
    return value


def unsigned(value):
    result = money(value)
    if result < 0:
        raise ValueError("INV-01 amounts must be unsigned; credit-note sign is applied on import")
    return result


def parse_invoice_json(content, data):
    if not data.gst_registration or not data.gst_direction or not data.gst_period:
        raise ValueError("Select the entity GSTIN, purchase/sale direction and reporting month")
    registration = gstin(data.gst_registration)
    documents = read_json_document(content)
    if isinstance(documents, dict):
        documents = [documents]
    if not isinstance(documents, list) or not documents or len(documents) > 1000:
        raise ValueError("Select one INV-01 object or a bounded non-empty array of invoice objects")
    rows, controls, identities = [], [], set()
    try:
        for ordinal, document in enumerate(documents, 1):
            if not isinstance(document, dict) or document.get("Version") != "1.1":
                raise ValueError("Only plain INV-01 version 1.1 invoice objects are supported")
            if any(
                key in document
                for key in ("SignedInvoice", "SignedQRCode", "CancelDate", "CancelDt")
            ):
                raise ValueError(
                    "Signed wrappers and cancellation events require their own verified adapter"
                )
            seller, buyer = (
                gstin(document["SellerDtls"]["Gstin"]),
                gstin(document["BuyerDtls"]["Gstin"]),
            )
            own, other = (buyer, seller) if data.gst_direction == "purchase" else (seller, buyer)
            if own != registration:
                raise ValueError(
                    "Invoice party does not agree to the selected entity GSTIN and direction"
                )
            transaction = document["TranDtls"]
            if transaction.get("TaxSch") != "GST" or transaction.get("SupTyp") not in {
                "B2B",
                "SEZWP",
                "SEZWOP",
                "DEXP",
            }:
                raise ValueError(
                    "This profile supports registered-party domestic/deemed-export/SEZ GST documents"
                )
            reverse = transaction.get("RegRev", "N")
            if reverse not in {"N", "Y"}:
                raise ValueError("Invalid reverse-charge indicator")
            doc = document["DocDtls"]
            types = {"INV": "invoice", "CRN": "credit-note", "DBN": "debit-note"}
            if (
                doc["Typ"] not in types
                or not isinstance(doc["No"], str)
                or not re.fullmatch(r"[A-Za-z0-9/\-]{1,16}", doc["No"])
            ):
                raise ValueError("Unsupported e-invoice document type or number")
            if not re.fullmatch(r"\d{2}/\d{2}/\d{4}", doc["Dt"]):
                raise ValueError("E-invoice date must use DD/MM/YYYY")
            when = datetime.strptime(doc["Dt"], "%d/%m/%Y").date()
            if when.strftime("%Y-%m") > data.gst_period:
                raise ValueError("Document date is after the selected reporting month")
            identity = (seller, doc["Typ"], doc["No"].casefold(), when.isoformat())
            if identity in identities:
                raise ValueError("Duplicate e-invoice document in the selected file")
            identities.add(identity)
            items = document["ItemList"]
            if not isinstance(items, list) or not items or len(items) > 5000:
                raise ValueError("E-invoice item population is missing or exceeds the bound")
            values = document["ValDtls"]
            assessed, item_total = Decimal(0), Decimal(0)
            taxes = {component: Decimal(0) for component in COMPONENTS}
            serials = set()
            for item in items:
                serial = item["SlNo"]
                if not isinstance(serial, str) or not serial or serial in serials:
                    raise ValueError("E-invoice item serials must be unique")
                serials.add(serial)
                base = money(item["AssAmt"])
                if base < 0:
                    raise ValueError(
                        "INV-01 amounts must be unsigned; credit-note sign is applied on import"
                    )
                assessed += base
                for component, (line_key, _) in COMPONENTS.items():
                    tax = unsigned(item.get(line_key, 0))
                    if component == "CESS":
                        tax += unsigned(item.get("CesNonAdvlAmt", 0))
                    elif component == "STATE_CESS":
                        tax += unsigned(item.get("StateCesNonAdvlAmt", 0))
                    if tax < 0:
                        raise ValueError("Negative e-invoice tax is unsupported")
                    taxes[component] += tax
                item_total += unsigned(item["TotItemVal"])
            if assessed != money(values["AssVal"]):
                raise ValueError("Invoice assessable value does not agree to its item population")
            for component, (_, header_key) in COMPONENTS.items():
                if taxes[component] != money(values.get(header_key, 0)):
                    raise ValueError("Invoice component tax does not agree to its item population")
            total = money(values["TotInvVal"])
            if (
                total < 0
                or item_total
                - unsigned(values.get("Discount", 0))
                + unsigned(values.get("OthChrg", 0))
                + money(values.get("RndOffAmt", 0))
                != total
            ):
                raise ValueError(
                    "Invoice total does not agree to items, charges, discount and rounding"
                )
            sign = -1 if doc["Typ"] == "CRN" else 1
            for component, tax in taxes.items():
                row = TaxDocument(
                    id=f"inv01:{ordinal}:{component}",
                    registration=registration,
                    counterparty=other,
                    reference=doc["No"],
                    period=data.gst_period,
                    date=when,
                    currency="INR",
                    document_type=types[doc["Typ"]],
                    net=assessed * sign,
                    tax=tax * sign,
                    component=component,
                ).model_dump(mode="json")
                row.update(
                    source_document=ordinal,
                    reverse_charge=reverse,
                    supply_type=transaction["SupTyp"],
                    irp_authenticity="NOT_VERIFIED",
                    credit_eligibility="NOT_DETERMINED",
                    native_zero_component=tax == 0,
                )
                rows.append(row)
            controls.append(
                {
                    "document": ordinal,
                    "item_count": len(items),
                    "assessable_value": str(assessed * sign),
                    "invoice_total": str(total * sign),
                }
            )
    except (KeyError, TypeError, AttributeError, OverflowError):
        raise ValueError(
            "Incomplete or malformed INV-01 structure; inspect the retained original"
        ) from None
    return rows, {
        "currency": "INR",
        "registration": registration,
        "direction": data.gst_direction,
        "reporting_month": data.gst_period,
        "schema_version": "INV-01/1.1",
        "schema_validation": "RECONCILIATION_FIELDS_ONLY_NOT_FULL_IRP_SUBMISSION_VALIDATION",
        "document_count": len(documents),
        "document_controls": controls,
        "row_grain": "FIVE_TAX_COMPONENTS_PER_DOCUMENT_INCLUDING_ZERO_COMPONENTS",
        "taxable_amount_basis": "DOCUMENT_ASSESSABLE_VALUE_REPEATED_BY_COMPONENT_NOT_ADDITIVE",
        "irp_authenticity": "NOT_VERIFIED",
        "portal_status": "NOT_VERIFIED",
        "itc_eligibility": "NOT_DETERMINED",
        "rate_validation": "NOT_PERFORMED",
    }
