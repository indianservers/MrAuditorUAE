def approval_error(body):
    if body.get("workflow") == "ownership-lookthrough" and body.get("ownership_path_contract") != "economic-ownership-paths/1":
        return "Regenerate ownership with retained complete source paths before independent approval"
    if body.get("workflow") == "procurement-match" and body.get("purchase_quantity_contract") != "controlled-purchase-quantities/1":
        return "Regenerate procurement with independently controlled quantities and explicit units before approval"
    if body.get("workflow") == "sanctions-name-review" and any(
        row.get("candidate_preview_truncated")
        or (row.get("candidate_count") is not None and row["candidate_count"] != len(row.get("candidates", [])))
        for row in body["rows"]
    ):
        return "Regenerate screening with complete retained candidates before independent approval"
    if body.get("bank_account_evidence",{}).get("status") == "LINK_REQUESTED_NOT_VERIFIED":
        return "Verify the requested bank account evidence link before independent approval"
    if body.get("workflow") == "india-withholding":
        return "Legacy aggregate withholding requires a new role-scoped liability or credit assessment"
    if body.get("blocked"):
        return "Resolve missing evidence, expired checks or balance controls and regenerate before approval"
    for row in body["rows"]:
        if (
            row["state"] not in {"MATCHED", "SUPPORTED", "NOT-APPLICABLE"}
            and row.get("auditor_status") != "EXCEPTION_DOCUMENTED"
        ):
            return (
                "Document the disposition of every workflow exception before independent approval"
            )
    return None
