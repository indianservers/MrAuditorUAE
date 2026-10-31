def approval_error(body):
    if body.get("workflow") == "uae-company-accounts-duty":
        from app.modules.country_workflows.uae_company_accounts import CONTRACT

        if (
            body.get("contract") != CONTRACT
            or body.get("company_accounts_document_binding") != "RETAINED_DOCUMENT_BYTES_VERIFIED"
        ):
            return "Regenerate the UAE company-law assessment with retained originals, legal adoption and company facts"
    if body.get("workflow") == "uae-ct-audit-duty":
        from app.modules.country_workflows.uae_ct_audit_duty import CONTRACT

        if (
            body.get("contract") != CONTRACT
            or body.get("ct_audit_document_binding") != "RETAINED_DOCUMENT_BYTES_VERIFIED"
        ):
            return "Regenerate the UAE corporate-tax audit duty with retained original rule and fact documents"
    if body.get("workflow") == "india-salary-annual-reconciliation":
        from app.modules.country_workflows.salary_annual_comparison import CONTRACT

        if (
            body.get("contract") != CONTRACT
            or body.get("salary_crosswalk_document_binding") != "RETAINED_DOCUMENT_BYTES_VERIFIED"
        ):
            return "Regenerate the four-quarter salary comparison with retained independent employee mapping"
    from app.modules.country_workflows.withholding_pan import approval_error as pan_error

    if error := pan_error(body):
        return error
    from app.modules.country_workflows.withholding_provisions import saved_withdrawn_expectation

    if saved_withdrawn_expectation(body):
        return "Correct the positive 206C(1H) expectation for the withdrawn period and regenerate before approval"
    if (
        body.get("workflow") == "stock-audit"
        and body.get("quantity_coverage_contract") != "stock-declared-count-coverage/1"
    ):
        return "Regenerate stock count coverage with the current quantity and sign controls before approval"
    from app.modules.intelligence.matching_review import saved_candidates_complete

    if body.get("workflow") == "inventory-performance" and (
        body.get("inventory_performance_contract") != "committed-inventory-performance/1"
        or body.get("inventory_performance_binding")
        != "COMMITTED_SNAPSHOT_ACCOUNT_CONTROLS_VERIFIED"
    ):
        return "Regenerate stock/GP comparison from current committed snapshots and independent account controls"

    if body.get("workflow") == "inventory-fifo-cost" and (
        body.get("inventory_fifo_contract") != "inventory-fifo-cost/1"
        or body.get("inventory_fifo_document_binding") != "RETAINED_DOCUMENT_BYTES_VERIFIED"
    ):
        return "Regenerate FIFO cost roll-forward with retained current cost/policy evidence"
    if body.get("workflow") == "tax-turnover-bridge":
        from app.modules.country_workflows.gst_annual_scope import saved_current

        if not saved_current(body):
            return "Regenerate annual GST candidates with the retained PAN scope"

    if body.get("workflow") == "uae-vat":
        from app.modules.country_workflows.uae_vat_currency import current

        if not current(body):
            return "Regenerate UAE VAT comparison with explicit AED reporting controls"

    if body.get("workflow") in {"india-gst", "india-gstr1-documents"}:
        from app.modules.country_workflows.gst_currency import current

        if not current(body):
            return "Regenerate India GST comparison with explicit INR reporting controls"

    if body.get("workflow") == "bank-account-evidence":
        from app.modules.country_workflows.bank_observation_scope import saved_scope

        try:
            saved_scope(body)
        except ValueError:
            return "Regenerate complete account observation coverage before approval"

    if body.get("workflow") == "india-msme-annual-tax":
        from app.modules.country_workflows.msme_tax_schemas import CONTRACT

        if body.get("msme_tax_contract") != CONTRACT or body.get(
            "msme_tax_document_binding"
        ) not in {"RETAINED_DOCUMENT_BYTES_VERIFIED", "NO_TAX_FACTS_CLAIMED"}:
            return "Regenerate MSE annual tax with retained expense, opening-tax and settlement support"
        if body.get("msme_tax_document_binding") == "NO_TAX_FACTS_CLAIMED" and any(
            row.get("tax_basis") or row.get("interest_pnl_assessment")
            for row in body.get("invoice_tax_details", [])
        ):
            return "Bind the declared MSE annual tax supporting documents before approval"

    if body.get("workflow") == "india-msme-interest":
        from app.modules.country_workflows.msme_interest_schemas import CONTRACT

        if body.get("msme_interest_contract") != CONTRACT or body.get(
            "msme_interest_document_binding"
        ) not in {"RETAINED_DOCUMENT_BYTES_VERIFIED", "NO_INTEREST_FACTS_CLAIMED"}:
            return "Regenerate MSE interest with retained policies, bank rates and principal-change documents"
        if body.get("msme_interest_document_binding") == "NO_INTEREST_FACTS_CLAIMED" and (
            any(row.get("interest_policy") for row in body.get("rows", []))
            or body.get("retained_interest_rate_rows")
        ):
            return "Bind the declared MSE interest policy and bank-rate documents before approval"

    if body.get("workflow") == "india-payroll-rules":
        from app.modules.country_workflows.payroll_calculations import CONTRACT

        if body.get("payroll_rule_selection_contract") != CONTRACT:
            return "Regenerate India payroll with current whole-month policy intersection checks"

    if body.get("workflow") == "uae-savings-review" and (
        body.get("savings_contribution_contract") != "uae-savings-basic-contributions/1"
        or body.get("savings_document_binding") != "RETAINED_DOCUMENT_BYTES_VERIFIED"
    ):
        return "Regenerate savings basic contributions with retained enrolment and rule documents"

    if body.get("workflow") == "india-payroll-basis-proration":
        from app.modules.country_workflows.payroll_basis_proration import CONTRACT

        if (
            body.get("payroll_proration_contract") != CONTRACT
            or body.get("monthly_basis_complete") is not True
        ):
            return (
                "Regenerate complete dated PF wage bases with current independent monthly controls"
            )

    if (
        body.get("workflow") == "uae-benefit-review"
        and body.get("service_calendar_basis") == "DATED_CONTROLLED_SOURCE"
    ):
        from app.modules.country_workflows.benefit_service_calendar import CONTRACT

        if body.get("benefit_service_calendar_contract") != CONTRACT:
            return "Regenerate dated benefit service-day checks before approval"

    if body.get("workflow") == "merchant-reserve-rollforward":
        from app.modules.country_workflows.merchant_reserves import CONTRACT

        if body.get("merchant_reserve_contract") != CONTRACT:
            return "Regenerate reserve continuity with dated components and exact ledger controls before approval"

    if body.get("workflow") == "merchant-settlement-bridge":
        from app.modules.country_workflows.merchant_settlements import CONTRACT

        if body.get("merchant_settlement_contract") != CONTRACT:
            return "Regenerate merchant settlement with unreversed booked-date evidence before approval"
    if body.get("workflow") in {
        "india-msme-payment-timing",
        "india-msme-interest",
        "india-msme-annual-tax",
    } and (
        body.get("msme_evidence_contract") != "retained-msme-context/1"
        or body.get("msme_document_binding")
        not in {"RETAINED_DOCUMENT_BYTES_VERIFIED", "NO_RESOLVED_FACTS_CLAIMED"}
    ):
        return "Regenerate MSE timing with current retained context documents before independent approval"
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
