"""Source-backed provenance and read-interface discovery; never invent financial values."""

from decimal import Decimal, localcontext

from defusedxml.ElementTree import fromstring

from app.modules.connectors.zoho import ConnectorError
from app.modules.ingestion.parser import money

QBO_TYPES = {
    "invoice": "invoice",
    "bill": "bill",
    "payment": "payment",
    "billpaymentcheck": "billpayment",
    "billpaymentcreditcard": "billpayment",
    "billpayment": "billpayment",
    "journalentry": "journalentry",
    "salesreceipt": "salesreceipt",
    "refundreceipt": "refundreceipt",
    "creditmemo": "creditmemo",
    "vendorcredit": "vendorcredit",
    "purchase": "purchase",
    "check": "purchase",
    "expense": "purchase",
    "deposit": "deposit",
    "transfer": "transfer",
    "creditcardcredit": "purchase",
}


def qbo_document_type(label):
    return QBO_TYPES.get("".join(c for c in label.lower() if c.isalnum()))


def match_qbo_posting(row: dict, document: dict):
    """Only assign a native line identity when account and base amount match uniquely."""
    candidates = []
    original_amounts = {}
    for line in document.get("Line", []):
        detail = line.get(line.get("DetailType", ""), {})
        account = detail.get("AccountRef", {}).get("value")
        if str(account) != row["account_code"] or not line.get("Id"):
            continue
        amount = money(str(line.get("Amount", "0")))
        rate = money(str(document.get("ExchangeRate", "1")))
        with localcontext() as numeric:
            numeric.prec = 48
            if amount * rate == money(row["debit"]) + money(row["credit"]):
                candidates.append(str(line["Id"]))
                original_amounts[str(line["Id"])] = amount
    if len(candidates) == 1:
        row = {
            **row,
            "source_id": ":".join(
                ["txn", row["source_transaction_id"], candidates[0], row["account_code"]]
            ),
            "source_line_id": candidates[0],
            "source_identity_quality": "matched_native_line",
        }
        original_currency = document.get("CurrencyRef", {}).get("value")
        source_rate = document.get("ExchangeRate")
        if original_currency and source_rate is not None:
            amount = original_amounts[candidates[0]]
            row = foreign_provenance(
                row,
                original_currency,
                amount if money(row["debit"]) else "0",
                amount if money(row["credit"]) else "0",
                source_rate,
            )
    else:
        row = {**row, "source_identity_quality": "snapshot_scoped_ambiguous"}
    return row


def foreign_provenance(row, currency, debit=None, credit=None, rate=None):
    result = {**row, "original_currency": currency or "", "source_fx_status": "not_supplied"}
    if debit is not None and credit is not None:
        original_debit, original_credit = money(str(debit)), money(str(credit))
        if original_debit < 0 or original_credit < 0 or original_debit and original_credit:
            raise ConnectorError("Invalid original-currency debit/credit")
        result.update(original_debit=str(original_debit), original_credit=str(original_credit))
        if rate is not None:
            from babel.numbers import get_currency_precision

            exchange = money(str(rate))
            tolerance = Decimal(1).scaleb(-get_currency_precision(row["currency"]))
            with localcontext() as numeric:
                numeric.prec = 48
                if exchange <= 0 or any(
                    abs(source * exchange - money(row[key])) > tolerance
                    for source, key in ((original_debit, "debit"), (original_credit, "credit"))
                ):
                    raise ConnectorError(
                        "Source original/base amounts conflict with the source exchange rate"
                    )
            result.update(
                source_exchange_rate=str(exchange), source_fx_status="source_rate_verified"
            )
    return result


def tax_evidence(document: dict, provider: str):
    if provider == "quickbooks":
        detail = document.get("TxnTaxDetail", {})
        lines = detail.get("TaxLine", [])
        amounts = [money(str(line["Amount"])) for line in lines if "Amount" in line]
        total = money(str(detail["TotalTax"])) if "TotalTax" in detail else None
        codes = [line.get("TaxLineDetail", {}).get("TaxRateRef", {}).get("value") for line in lines]
    else:
        lines = document.get("taxes", [])
        amounts = [money(str(line["tax_amount"])) for line in lines if "tax_amount" in line]
        total = money(str(document["tax_total"])) if "tax_total" in document else None
        codes = [line.get("tax_id") for line in lines]
    return {
        "tax_total": str(total) if total is not None else None,
        "source_tax_codes": [str(code) for code in codes if code],
        "components_match": sum(amounts, Decimal(0)) == total
        if total is not None and len(amounts) == len(lines) and lines
        else None,
        "jurisdiction": document.get("place_of_supply") or document.get("Country", ""),
        "interpretation": "source_data_only; no inferred GST/VAT treatment",
    }


def odata_metadata(xml: bytes, entity_set: str, required_fields: set[str]):
    if len(xml) > 8 * 1024 * 1024:
        raise ConnectorError("OData metadata exceeds 8 MiB")
    try:
        root = fromstring(xml)
    except Exception:
        raise ConnectorError("Invalid or unsafe OData metadata XML") from None
    schemas = [n for n in root.iter() if n.tag.split("}")[-1] == "Schema"]
    aliases = {n.get("Alias"): n.get("Namespace") for n in schemas if n.get("Alias")}
    types = {}
    sets = {}

    def qualified(name):
        prefix, _, suffix = name.rpartition(".")
        return (aliases.get(prefix) or prefix) + "." + suffix if prefix else name

    for schema in schemas:
        namespace = schema.get("Namespace", "")
        for node in schema:
            if node.tag.split("}")[-1] == "EntityType":
                name = namespace + "." + node.get("Name", "") if namespace else node.get("Name", "")
                if name in types:
                    raise ConnectorError("Ambiguous OData entity type")
                types[name] = node
        for node in schema.iter():
            if node.tag.split("}")[-1] == "EntitySet":
                name = node.get("Name", "")
                if name in sets:
                    raise ConnectorError("Ambiguous OData entity set")
                sets[name] = qualified(node.get("EntityType", ""))
    type_name = sets.get(entity_set)
    if not type_name:
        raise ConnectorError("Configured OData entity is not published by the source")
    fields: dict[str, str] = {}
    seen = set()
    while type_name:
        if type_name in seen:
            raise ConnectorError("Cyclic OData entity inheritance")
        seen.add(type_name)
        entity = types.get(type_name)
        if entity is None:
            # Some test/legacy metadata omits the Schema namespace. Accept only
            # an unambiguous unqualified type, never combine namespaces.
            entity = types.get(type_name.rsplit(".", 1)[-1])
        if entity is None:
            raise ConnectorError("OData entity type definition is unavailable")
        for node in entity:
            if node.tag.split("}")[-1] == "Property":
                fields.setdefault(node.get("Name", ""), node.get("Type", ""))
        type_name = qualified(entity.get("BaseType", "")) if entity.get("BaseType") else ""
    missing = required_fields - fields.keys()
    if missing:
        raise ConnectorError(
            "Deployed OData contract is missing fields: " + ", ".join(sorted(missing))
        )
    return {
        "entity_set": entity_set,
        "fields_verified": sorted(required_fields),
        "property_types": fields,
    }
