import asyncio
import json

import httpx

from app.modules.ai_engine.schemas import AIRequest, AIResponse, Summary
from app.modules.financial_ai.schemas import OUTPUTS


class ProviderFailure(Exception):
    pass


class MockProvider:
    async def generate(self, request: AIRequest) -> AIResponse:
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
                                    "schema": OUTPUTS.get(
                                        request.task_type, Summary
                                    ).model_json_schema(),
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
                        output=OUTPUTS.get(request.task_type, Summary).model_validate(
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
