"""Reviewed recipes, not model-authored executable plans."""

TOOLS = {
    "financial.get_general_ledger": ("financial", "accounting.read", "ledger"),
    "financial.get_trial_balance": ("financial", "accounting.read", "balance"),
    "financial.get_reconciliation": ("financial", "analytics.read", "reconciliation"),
    "audit.get_risks": ("audit", "audit.read", "risks"),
    "audit.get_working_papers": ("audit", "audit.read", "working-papers"),
    "audit.get_analytics": ("audit", "analytics.read", "analytics"),
    "audit.get_shared_workflows": ("audit", "accounting.read", "shared-workflows"),
    "audit.get_evidence": ("audit", "audit.read", "evidence"),
    "ifrs.get_financial_statements": ("ifrs", "ifrs.read", "ifrs-run"),
    "ifrs.get_schedules": ("ifrs", "ifrs.read", "ifrs-records"),
    "tax.get_ct_computation": ("tax", "tax.profile.read", "tax-run"),
    "tax.get_qfzp_assessment": ("tax", "tax.profile.read", "tax-qfzp"),
    "tax.get_interest_schedule": ("tax", "tax.profile.read", "tax-interest"),
    "vat.get_reconciliation": ("vat", "vat.read", "vat-run"),
    "vat.get_invoice_exceptions": ("vat", "vat.read", "vat-invoice"),
    "tp.get_related_party_transactions": ("tp", "tp.read", "tp-transaction"),
    "tp.get_benchmark_study": ("tp", "tp.read", "tp-study"),
    "tp.get_loan_analysis": ("tp", "tp.read", "tp-loan"),
    "dmtt.get_scope_assessment": ("dmtt", "dmtt.read", "dmtt-group"),
    "dmtt.get_etr_calculation": ("dmtt", "dmtt.read", "dmtt-run"),
    "grc.get_controls": ("grc", "grc.read", "grc-control"),
    "grc.get_monitoring_alerts": ("grc", "monitor.alert.review", "alerts"),
    "grc.get_remediation_actions": ("grc", "grc.read", "grc-remediation"),
    "ml.get_predictions": ("ml", "ml.read", "inference"),
    "ml.get_model_evaluations": ("ml", "ml.read", "model"),
    "documents.search": ("documents", "audit.read", "search"),
    "documents.get_authorized_excerpt": ("documents", "audit.read", "excerpt"),
    "quality.validate_sources": ("quality", "ai.investigation.read", "quality"),
}

AGENT_NAMES = {
    "orchestrator": "Audit Orchestrator",
    "financial": "Financial Data Agent",
    "audit": "External Audit Agent",
    "ifrs": "IFRS Reporting Agent",
    "tax": "UAE Corporate Tax Agent",
    "vat": "UAE VAT Agent",
    "tp": "Transfer Pricing Agent",
    "dmtt": "Pillar Two / DMTT Agent",
    "grc": "Internal Audit & GRC Agent",
    "documents": "Document Intelligence Agent",
    "ml": "TensorFlow.js ML Investigation Agent",
    "quality": "Quality & Professional Review Agent",
}

RECIPES = {
    "revenue": [
        "financial.get_general_ledger",
        "audit.get_analytics",
        "ml.get_predictions",
        "ifrs.get_schedules",
        "audit.get_risks",
        "vat.get_invoice_exceptions",
        "tp.get_related_party_transactions",
        "documents.search",
    ],
    "corporate-tax": [
        "ifrs.get_financial_statements",
        "tax.get_ct_computation",
        "financial.get_general_ledger",
        "documents.search",
    ],
    "qfzp": ["tax.get_qfzp_assessment", "ifrs.get_financial_statements", "documents.search"],
    "transfer-pricing": [
        "tp.get_related_party_transactions",
        "tp.get_benchmark_study",
        "tp.get_loan_analysis",
        "documents.search",
    ],
    "pillar-two": ["dmtt.get_scope_assessment", "dmtt.get_etr_calculation", "documents.search"],
    "document-ledger": ["documents.search", "financial.get_general_ledger", "audit.get_evidence"],
    "grc-monitoring": [
        "grc.get_monitoring_alerts",
        "grc.get_controls",
        "grc.get_remediation_actions",
    ],
    "audit-planning": [
        "financial.get_trial_balance",
        "audit.get_risks",
        "audit.get_working_papers",
    ],
    "monthly-anomalies": [
        "audit.get_analytics",
        "ml.get_predictions",
        "financial.get_general_ledger",
    ],
    "reconciliation": ["audit.get_shared_workflows", "financial.get_reconciliation", "financial.get_general_ledger"],
    "evidence-request": ["audit.get_evidence", "documents.search"],
    "workpaper-review": ["audit.get_working_papers", "audit.get_risks"],
    "vat-exceptions": ["vat.get_reconciliation", "vat.get_invoice_exceptions"],
    "loan-interest": [
        "tp.get_loan_analysis",
        "tax.get_interest_schedule",
        "financial.get_general_ledger",
    ],
    "ifrs-disclosure": ["ifrs.get_financial_statements", "ifrs.get_schedules", "documents.search"],
}
ALIASES = {
    "revenue": "revenue",
    "corporate tax": "corporate-tax",
    "qfzp": "qfzp",
    "related-party": "transfer-pricing",
    "transfer pricing": "transfer-pricing",
    "pillar two": "pillar-two",
    "dmtt": "pillar-two",
    "invoice": "document-ledger",
    "grc": "grc-monitoring",
    "control": "grc-monitoring",
    "reconciliation": "reconciliation",
    "loan": "loan-interest",
    "disclosure": "ifrs-disclosure",
    "planning": "audit-planning",
    "vat": "vat-exceptions",
}

READ = {
    "ai.chat.use",
    "ai.investigation.create",
    "ai.investigation.read",
    "ai.workflow.run",
    "ai.approval.request",
    "ai.documents.index",
}
REVIEW = {
    "ai.approval.decide",
    "ai.workflow.schedule",
    "ai.usage.read",
    "ai.auditlog.read",
    "ai.model.evaluate",
    "ai.knowledge.manage",
}
ADMIN = {"ai.agent.configure", "ai.tools.manage", "ai.provider.manage"}


def agents():
    return [
        {
            "id": key,
            "description": name,
            "task_types": [
                k
                for k, tools in RECIPES.items()
                if key == "orchestrator"
                or any(TOOLS[t][0] == key for t in tools)
                or key == "quality"
            ],
            "allowed_tools": [t for t, meta in TOOLS.items() if meta[0] == key],
            "required_permissions": sorted({v[1] for v in TOOLS.values() if v[0] == key}),
            "input_schema": "ToolInput/v1",
            "output_schema": "ToolResult/v1",
            "prompt_version": "enterprise-ai/1",
            "max_tool_calls": 12,
            "max_duration_seconds": 90,
            "max_context_characters": 11000,
            "max_output_tokens": 1000,
            "cost_budget": "external calls disabled unless explicitly approved in existing gateway",
            "error_policy": "record bounded failure; preserve partial state",
            "approval_policy": "propose only; independent professional review",
            "audit_logging": True,
        }
        for key, name in AGENT_NAMES.items()
    ]


def plan(task: str | None, prompt: str):
    if task is None:
        matches = {v for k, v in ALIASES.items() if k in prompt.lower()}
        if len(matches) != 1:
            raise ValueError(
                "Select an explicit supported task; intent is ambiguous or unsupported"
            )
        task = matches.pop()
    if task not in RECIPES:
        raise ValueError("Unsupported task")
    return task, [*RECIPES[task], "quality.validate_sources"]
