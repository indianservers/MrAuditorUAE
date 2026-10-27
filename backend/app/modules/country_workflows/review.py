def approval_error(body):
    from app.modules.intelligence.matching_review import saved_candidates_complete

    if body.get("workflow") == "bank-brs" and not saved_candidates_complete(body):
        return (
            "Regenerate bank matching with complete retained ambiguity candidates before approval"
        )
    if body.get("workflow") == "adverse-media-review" and (
        body.get("media_review_contract") != "retained-adverse-media/1"
        or body.get("media_document_binding") != "RETAINED_DOCUMENT_BYTES_VERIFIED"
    ):
        return "Regenerate media review with current retained search, article, identity and policy evidence before approval"
    if body.get("workflow") == "grant-utilisation" and (
        body.get("grant_utilisation_contract") != "mandate-expenditure-allocation/1"
        or body.get("grant_document_binding") != "RETAINED_DOCUMENT_BYTES_VERIFIED"
    ):
        return "Regenerate grant utilisation with current retained mandate and recovery evidence before independent approval"
    if (
        body.get("workflow") == "ownership-lookthrough"
        and body.get("ownership_path_contract") != "economic-ownership-paths/1"
    ):
        return (
            "Regenerate ownership with retained complete source paths before independent approval"
        )
    if (
        body.get("workflow") == "procurement-match"
        and body.get("purchase_quantity_contract") != "controlled-purchase-quantities/1"
    ):
        return "Regenerate procurement with independently controlled quantities and explicit units before approval"
    if body.get("workflow") == "sanctions-name-review" and any(
        row.get("candidate_preview_truncated")
        or (
            row.get("candidate_count") is not None
            and row["candidate_count"] != len(row.get("candidates", []))
        )
        for row in body["rows"]
    ):
        return "Regenerate screening with complete retained candidates before independent approval"
    if body.get("bank_account_evidence", {}).get("status") == "LINK_REQUESTED_NOT_VERIFIED":
        return "Verify the requested bank account evidence link before independent approval"
    if body.get("workflow") == "india-withholding":
        return (
            "Legacy aggregate withholding requires a new role-scoped liability or credit assessment"
        )
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
