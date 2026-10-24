"""QuickBooks events are repair hints, never a general-ledger population."""

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

from app.modules.connectors.zoho import ConnectorError

CDC_ENTITIES = {
    "Account",
    "Bill",
    "BillPayment",
    "CreditMemo",
    "Deposit",
    "Invoice",
    "JournalEntry",
    "Payment",
    "Purchase",
    "RefundReceipt",
    "SalesReceipt",
    "Transfer",
    "VendorCredit",
}


def verify_quickbooks(body: bytes, signature: str, verifier: str):
    if not verifier or len(body) > 65536:
        raise ConnectorError(
            "QuickBooks webhook verification is not configured or payload is too large"
        )
    expected = base64.b64encode(hmac.digest(verifier.encode(), body, "sha256")).decode()
    if not hmac.compare_digest(expected, signature):
        raise ConnectorError("QuickBooks webhook signature is invalid")
    try:
        data = json.loads(body)
    except ValueError:
        raise ConnectorError("Invalid webhook JSON") from None
    if not isinstance(data, dict) or not isinstance(data.get("eventNotifications"), list):
        raise ConnectorError("Invalid webhook envelope")
    events = []
    for notification in data.get("eventNotifications", []):
        if not isinstance(notification, dict) or not isinstance(
            notification.get("dataChangeEvent"), dict
        ):
            raise ConnectorError("Invalid webhook notification")
        realm = str(notification.get("realmId", ""))
        if not realm.isdigit():
            raise ConnectorError("Webhook realm is invalid")
        entities = notification["dataChangeEvent"].get("entities")
        if not isinstance(entities, list) or not all(isinstance(item, dict) for item in entities):
            raise ConnectorError("Invalid webhook entities")
        for item in entities:
            if item.get("name") not in CDC_ENTITIES:
                continue
            if item.get("operation") not in {"Create", "Update", "Delete", "Void", "Merge"}:
                raise ConnectorError("Unsupported webhook operation")
            identity = str(item.get("id", ""))
            if not identity.isdigit():
                raise ConnectorError("Webhook entity identifier is invalid")
            stamp = datetime.fromisoformat(str(item["lastUpdated"]).replace("Z", "+00:00"))
            if stamp.tzinfo is None or stamp > datetime.now(UTC) + timedelta(minutes=5):
                raise ConnectorError("Webhook update time is invalid")
            event = {
                "realm_id": realm,
                "entity": item["name"],
                "id": identity,
                "operation": item["operation"],
                "last_updated": stamp.isoformat(),
            }
            event["key"] = hashlib.sha256(json.dumps(event, sort_keys=True).encode()).hexdigest()
            events.append(event)
    return events


def cdc_parameters(since: datetime, entities: list[str]):
    now = datetime.now(UTC)
    if since.tzinfo is None or not now - timedelta(days=30) <= since <= now:
        raise ConnectorError("QuickBooks CDC repair must be within the supported 30-day window")
    if not entities or set(entities) - CDC_ENTITIES:
        raise ConnectorError("CDC contains unsupported entities")
    return {
        "entities": ",".join(sorted(set(entities))),
        "changedSince": since.astimezone(UTC).isoformat(),
    }
