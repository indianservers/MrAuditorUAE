"""Fictional purchase and sale originals; neither is filed-return evidence."""

import json


async def prepare(client, headers, engagement, reviewer, retain):
    from app.modules.country_workflows.schemas import TaxDocument
    from tests.qa_crud.test_country_workflows import decision, execute, source
    from tests.unit.test_india_invoice_source import BUYER, SELLER, invoice

    result = {}
    for direction in ("purchase", "sale"):
        document = invoice()
        if direction == "sale":
            document["SellerDtls"]["Gstin"] = BUYER
            document["BuyerDtls"]["Gstin"] = SELLER
            document["DocDtls"]["No"] = "SYN-SALE-1"
        evidence = await retain(engagement, f"SYNTHETIC-{direction}-invoice.json", json.dumps(document).encode(), "application/json")
        native = await execute(client, headers, engagement, "workflow-source", {
            "evidence_version_id": evidence, "file_format": "india-inv01-json", "table_type": "tax-documents",
            "label": f"SYNTHETIC {direction} invoice evidence", "expected_rows": 5, "control_totals": {"INR": "18"},
            "gst_registration": BUYER, "gst_direction": direction, "gst_period": "2026-06",
        })
        register_row = {key: value for key, value in native["body"]["rows"][0].items() if key in TaxDocument.model_fields}
        register_row["id"] = "REGISTER-" + direction
        register = await source(client, headers, engagement, [register_row], f"SYNTHETIC {direction} register", "tax-documents", {"INR": "18"})
        selected = {}
        for role, event in (("books", register), ("invoices", native)):
            approved = await decision(client, reviewer[0], engagement, event)
            assert approved.status_code == 201, approved.text
            selected[role] = approved.json()["id"]
        result[direction] = selected
    return result
