"""File compatibility never implies a qualified live provider adapter."""

PROVIDERS = [
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
        {"id": key, "name": name, "adapter": None, "status": "adapter_not_implemented"}
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
