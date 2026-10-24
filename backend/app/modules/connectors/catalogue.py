"""File compatibility never implies a qualified live provider adapter."""

from typing import Any

PROVIDERS: list[dict[str, Any]] = [
    {
        "id": "tally",
        "name": "TallyPrime",
        "adapter": "local-agent-and-xml",
        "status": "environment_qualification_pending",
    },
    {
        "id": "zoho",
        "name": "Zoho Books",
        "adapter": "oauth-api",
        "status": "credentials_qualification_pending",
    },
    *[
        {
            "id": key,
            "name": name,
            "adapter": "configured-partner-api" if key in {"busy", "marg"} else "direct-vendor-api",
            "status": "partner_contract_required"
            if key in {"busy", "marg"}
            else "credentials_qualification_pending",
            "live_api_status": "partner_transport_implemented"
            if key in {"busy", "marg"}
            else "adapter_implemented",
        }
        for key, name in [
            ("busy", "Busy Accounting"),
            ("marg", "Marg ERP"),
            ("sap-b1", "SAP Business One"),
            ("sap-s4", "SAP S/4HANA"),
            ("netsuite", "Oracle NetSuite"),
            ("quickbooks", "QuickBooks"),
            ("dynamics", "Microsoft Dynamics"),
            ("xero", "Xero"),
        ]
    ],
    {"id": "file", "name": "Excel / CSV", "adapter": "file", "status": "file_import_available"},
]

# Report support is distinct from qualification of a live installation/account.
for provider in PROVIDERS:
    provider["import_kinds"] = ["gl", "tb", "coa", "journals"]
    provider["file_formats"] = ["csv", "xlsx"]
    provider["report_set"] = "GL + opening/movement/closing TB + chart of accounts"
    provider["live_qualified"] = False

REQUIREMENTS = {
    "tally": [
        "TallyPrime version and test company",
        "Local HTTP/XML enabled on loopback port 9000",
        "Authorized AuditOS import identity",
        "Financial period and source GL/TB reports",
    ],
    "zoho": [
        "Zoho Books region and organization ID",
        "OAuth client ID/secret in secure configuration",
        "Registered allowlisted callback URL and read-only consent",
        "Source GL/TB reports",
    ],
    "busy": [
        "Busy edition/version and test company",
        "Flat GL, TB and account-master exports",
        "Vendor-approved partner API endpoints and response contract",
    ],
    "marg": [
        "Marg ERP edition/version and test company",
        "Flat GL, TB and account-master exports",
        "Licensed Marg Gateway URLs and response documentation",
    ],
    "sap-b1": [
        "SAP Business One version and company database",
        "GL/TB/account exports",
        "Service Layer endpoint and read-only user for direct synchronization",
    ],
    "sap-s4": [
        "S/4HANA edition and company code/ledger",
        "GL/TB/account exports",
        "Approved released API and communication arrangement for direct synchronization",
    ],
    "netsuite": [
        "NetSuite account and subsidiary/accounting book",
        "GL/TB/account exports",
        "Read-only integration role and approved SuiteQL access for direct synchronization",
    ],
    "quickbooks": [
        "QuickBooks Online or Desktop edition and company",
        "GL/TB/account exports",
        "Online OAuth app/realm or Desktop SDK access for direct synchronization",
    ],
    "dynamics": [
        "Business Central or Finance edition and company",
        "GL/TB/account exports",
        "Entra app and approved API permissions for direct synchronization",
    ],
    "xero": [
        "Xero test organization",
        "GL/TB/account exports",
        "OAuth app and journal/report access entitlement for direct synchronization",
    ],
    "file": ["Flat GL, TB and chart exports", "Entity, financial period and functional currency"],
}
