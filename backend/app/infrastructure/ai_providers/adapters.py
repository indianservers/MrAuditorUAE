import asyncio
import json

import httpx

from app.modules.ai_engine.schemas import AIRequest, AIResponse, Summary
from app.modules.audit_execution.ai_output import AuditAIOutput
from app.modules.financial_ai.schemas import OUTPUTS
from app.modules.tax.ai_output import TaxAIOutput
from app.modules.tp.ai_output import TPAIOutput
from app.modules.vat.ai_output import VATAIOutput


def output_schema(task):
    if task.startswith("tp_v8_"):
        return TPAIOutput
    if task.startswith("vat_v7_"):
        return VATAIOutput
    if task.startswith(("tax_v6_", "dmtt_v9_")):
        return TaxAIOutput
    return (
        AuditAIOutput
        if task.startswith(("audit_v4_", "grc_v10_", "enterprise_ai_v11_"))
        else OUTPUTS.get(task, Summary)
    )


class ProviderFailure(Exception):
    pass


class MockProvider:
    async def generate(self, request: AIRequest) -> AIResponse:
        if request.task_type.startswith("tp_v8_"):
            evidence = json.loads(request.text)
            return AIResponse(
                output=TPAIOutput(
                    issue=evidence["task"],
                    relevant_facts=["Synthetic supplied facts require independent verification"],
                    applicable_legislation=evidence["legal_references"],
                    tax_period=evidence["tax_period"],
                    analysis="MOCK DIAGNOSTIC ONLY. No economic research, loan OCR, market data retrieval or arm's length determination performed.",
                    potential_treatment="Undetermined pending professional economic review",
                    missing_facts=["Authorized comparable evidence and economic assessment"],
                    uncertainties=[
                        "Substantive comparability and legal scope not independently established"
                    ],
                    supporting_references=evidence["evidence_ids"],
                    required_human_action="Review original evidence, licensed source data and deterministic calculations; record an independent decision",
                    requires_human_review=True,
                    tax_position_approved=False,
                    economic_risks=[
                        "Unsupported comparable or market-rate inferences are prohibited"
                    ],
                    comparable_information_verified=False,
                    arms_length_conclusion_approved=False,
                ),
                input_tokens=max(1, len(request.text.split())),
                output_tokens=100,
                usage_source="mock_word_estimate",
            )
        if request.task_type.startswith("vat_v7_"):
            evidence = json.loads(request.text)
            return AIResponse(
                output=VATAIOutput(
                    issue=evidence["task"],
                    relevant_facts=["Selected synthetic source facts; require human verification"],
                    applicable_legislation=evidence["legal_references"],
                    tax_period=evidence["tax_period"],
                    analysis="MOCK DIAGNOSTIC ONLY: no semantic VAT research or visual OCR performed.",
                    potential_treatment="Undetermined pending professional review",
                    missing_facts=["Original evidence and applicable conditions"],
                    uncertainties=["Classification and evidence completeness not established"],
                    supporting_references=evidence["evidence_ids"],
                    required_human_action="Verify source facts and dated rules; approve any figure change separately",
                    requires_human_review=True,
                    tax_position_approved=False,
                    risk="Unreviewed legal treatment",
                    extracted_fields={},
                    document_processing="NOT_PROCESSED",
                ),
                input_tokens=len(request.text.split()),
                output_tokens=100,
                usage_source="mock_word_estimate",
            )
        if request.task_type.startswith(("tax_v6_", "dmtt_v9_")):
            evidence = json.loads(request.text)
            return AIResponse(
                output=TaxAIOutput(
                    issue=evidence["task"],
                    relevant_facts=["Supplied source records require verification"],
                    applicable_legislation=evidence["legal_references"],
                    tax_period=evidence["tax_period"],
                    analysis="MOCK DIAGNOSTIC ONLY: no semantic legal analysis performed.",
                    potential_treatment="Undetermined pending professional review",
                    missing_facts=["Verify original documents and contradictory evidence"],
                    uncertainties=["Legal eligibility and source completeness not established"],
                    supporting_references=evidence["evidence_ids"],
                    required_human_action="Review facts and approved period-specific legislation; record an independent decision",
                    requires_human_review=True,
                    tax_position_approved=False,
                ),
                input_tokens=len(request.text.split()),
                output_tokens=80,
                usage_source="mock_word_estimate",
            )
        if request.task_type.startswith(("audit_v4_", "grc_v10_", "enterprise_ai_v11_")):
            evidence = json.loads(request.text)
            return AIResponse(
                output=AuditAIOutput(
                    summary="MOCK DIAGNOSTIC ONLY: professional review of the supplied source records is required.",
                    observations=[
                        "Diagnostic transport output; no semantic audit analysis performed"
                    ],
                    proposed_procedures=[],
                    missing_information=["Inspect original evidence"],
                    citations=evidence["evidence_ids"],
                    requires_human_review=True,
                    evidence_sufficiency_determined=False,
                    opinion_issued=False,
                ),
                input_tokens=len(request.text.split()),
                output_tokens=50,
                usage_source="mock_word_estimate",
            )
        if request.task_type in OUTPUTS:
            evidence = json.loads(request.text)
            data = {
                "explanation": "Mock suggestion: the supplied evidence requires professional investigation; causation is not established.",
                "citations": evidence.get("evidence_ids", []),
                "requires_review": True,
            }
            if request.task_type == "account_classification":
                data.update(
                    proposed_classification="Unclassified",
                    statement_group="Pending professional classification",
                    confidence="low",
                )
            elif request.task_type == "anomaly_explanation":
                data.update(
                    potential_issues=["Review the deterministic indicator"],
                    verification_steps=["Inspect original supporting documentation"],
                    evidence_requirements=["Original voucher and authorization"],
                )
            elif request.task_type == "audit_procedures":
                data.update(
                    suggested_tests=["Trace selected entries to approved evidence"],
                    evidence_requests=["Voucher and supporting documents"],
                    assertions=evidence.get("assertions", []),
                    reviewer_notes="Professional review required",
                )
            else:
                data.update(
                    causation_established=False,
                    investigation_areas=["Determine documented causes"],
                    management_questions=["What evidence explains the calculated movement?"],
                )
            return AIResponse(
                output=OUTPUTS[request.task_type].model_validate(data),
                input_tokens=len(request.text.split()),
                output_tokens=50,
                usage_source="mock_word_estimate",
            )
        # Deterministic transport diagnostic; explicitly not a semantic model summary.
        summary = "Mock diagnostic excerpt: " + request.text[: min(200, request.max_tokens)]
        return AIResponse(
            output=Summary(summary=summary),
            input_tokens=len(request.text.split()),
            output_tokens=len(summary.split()),
            usage_source="mock_word_estimate",
        )


class OpenAICompatibleProvider:
    def __init__(self, base_url: str, key: str, timeout: float = 20):
        self.base_url, self.key, self.timeout = base_url.rstrip("/"), key, timeout

    async def generate(self, request: AIRequest) -> AIResponse:
        if not self.key and not self.base_url.startswith(
            ("http://localhost:", "http://127.0.0.1:")
        ):
            raise ProviderFailure("Provider credential unavailable")
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout, follow_redirects=False
                ) as client:
                    response = await client.post(
                        self.base_url + "/chat/completions",
                        headers={
                            "Authorization": "Bearer " + self.key,
                            "X-Request-ID": request.request_id,
                        },
                        json={
                            "model": request.model,
                            "messages": [
                                {"role": "system", "content": request.system_prompt},
                                {"role": "user", "content": request.text},
                            ],
                            "max_tokens": request.max_tokens,
                            "response_format": {
                                "type": "json_schema",
                                "json_schema": {
                                    "name": "summary",
                                    "strict": True,
                                    "schema": output_schema(request.task_type).model_json_schema(),
                                },
                            },
                        },
                    )
                    if response.status_code == 429 or response.status_code >= 500:
                        if attempt < 2:
                            await asyncio.sleep(0.25 * 2**attempt)
                            continue
                    response.raise_for_status()
                    if len(response.content) > 65536:
                        raise ProviderFailure("Provider output exceeds limit")
                    data = response.json()
                    usage = data.get("usage", {})
                    return AIResponse(
                        output=output_schema(request.task_type).model_validate(
                            json.loads(data["choices"][0]["message"]["content"])
                        ),
                        input_tokens=usage.get("prompt_tokens"),
                        output_tokens=usage.get("completion_tokens"),
                        usage_source="provider_reported" if usage else "unavailable",
                    )
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt == 2:
                    raise ProviderFailure("Provider transport failed") from None
                await asyncio.sleep(0.25 * 2**attempt)
            except httpx.HTTPStatusError:
                raise ProviderFailure("Provider rejected request") from None
        raise ProviderFailure("Provider exhausted retries")
