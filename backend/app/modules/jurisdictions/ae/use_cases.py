import json
from pathlib import Path

from pydantic import Field

from app.modules.audit_execution.schemas import Strict


class Calculation(Strict):
    family: str
    kind: str
    operation: str


class UseCase(Strict):
    id: int = Field(ge=1, le=200)
    key: str
    title: str
    description: str
    prompt: str
    engines: list[str]
    required_information: list[str]
    input_kinds: list[str]
    calculation: Calculation | None
    workflow: str | None
    phase: int
    scope_status: str
    completion_status: str
    limitations: list[str]
    legal_source_ids: list[str] = Field(default_factory=list)


MANIFEST = json.loads(Path(__file__).with_name("use_cases.json").read_text(encoding="utf-8"))
CASES = {row["id"]: UseCase.model_validate(row) for row in MANIFEST["items"]}

ENGINE_TOOLS = {
    "E01": "uae.get_case_inputs",
    "E02": "documents.search",
    "E03": "financial.get_trial_balance",
    "E04": "vat.get_reconciliation",
    "E05": "tax.get_ct_computation",
    "E06": "tax.get_qfzp_assessment",
    "E07": "tp.get_related_party_transactions",
    "E08": "dmtt.get_scope_assessment",
    "E09": "ifrs.get_schedules",
    "E10": "audit.get_risks",
    "E11": "audit.get_analytics",
    "E12": "audit.get_shared_workflows",
    "E13": "audit.get_shared_workflows",
    "E14": "financial.get_reconciliation",
    "E15": "ifrs.get_schedules",
    "E16": "audit.get_shared_workflows",
    "E17": "ifrs.get_schedules",
    "E18": "ifrs.get_financial_statements",
    "E19": "uae.get_case_inputs",
    "E20": "audit.get_evidence",
    "E21": "uae.get_case_inputs",
    "E22": "connections.get_health",
}


def recipe(case: UseCase):
    if case.id == 50:
        return [
            "uae.get_case_inputs",
            "financial.get_trial_balance",
            "vat.get_reconciliation",
            "tax.get_ct_computation",
            "ifrs.get_financial_statements",
            "audit.get_risks",
            "audit.get_shared_workflows",
            "tp.get_related_party_transactions",
            "dmtt.get_scope_assessment",
            "documents.search",
            "connections.get_health",
        ]
    # A bounded reviewed collection graph, never executable text from a document/model.
    tools = list(dict.fromkeys(["uae.get_case_inputs", *(ENGINE_TOOLS[e] for e in case.engines)]))
    if case.id>=151 and "E11" in case.engines:
        tools = list(dict.fromkeys([*tools, "ml.get_predictions", "ml.get_model_evaluations"]))
    return tools  # Existing orchestrator appends its quality/source validation step.
