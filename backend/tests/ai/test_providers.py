import json

import httpx
import pytest
from pydantic import ValidationError

from app.infrastructure.ai_providers.adapters import (
    MockProvider,
    OpenAICompatibleProvider,
    ProviderFailure,
)
from app.modules.ai_engine.schemas import AIRequest, ExecuteRequest


@pytest.fixture
def request_data():
    return AIRequest(
        text="Harmless diagnostic text.",
        model="mock-diagnostic",
        system_prompt="Return JSON",
        max_tokens=100,
        request_id="test-request",
    )


async def test_mock_deterministic(request_data):
    adapter = MockProvider()
    one = await adapter.generate(request_data)
    two = await adapter.generate(request_data)
    assert one == two and one.output.summary.startswith("Mock diagnostic")
    assert one.input_tokens > 0 and one.output_tokens > 0


async def test_real_missing_credentials(request_data):
    with pytest.raises(ProviderFailure):
        await OpenAICompatibleProvider("https://example.invalid/v1", "").generate(request_data)


@pytest.mark.parametrize(
    "kind",
    [
        "success",
        "invalid-json",
        "invalid-schema",
        "unauthorized",
        "server-retry",
        "timeout",
        "oversized",
    ],
)
async def test_real_adapter_transport(monkeypatch, request_data, kind):
    calls = []

    async def post(self, url, **kwargs):
        calls.append(kwargs)
        req = httpx.Request("POST", url)
        if kind == "timeout":
            raise httpx.ReadTimeout("timeout", request=req)
        if kind == "unauthorized":
            return httpx.Response(401, request=req)
        if kind == "server-retry" and len(calls) < 3:
            return httpx.Response(503, request=req)
        content = json.dumps({"summary": "A safe summary"})
        if kind == "invalid-json":
            content = "not-json"
        if kind == "invalid-schema":
            content = json.dumps({"code": "danger"})
        if kind == "oversized":
            content = "x" * 70000
        return httpx.Response(
            200,
            request=req,
            json={
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 3},
            },
        )

    async def no_sleep(delay):
        pass

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    monkeypatch.setattr("app.infrastructure.ai_providers.adapters.asyncio.sleep", no_sleep)
    provider = OpenAICompatibleProvider("https://example.invalid/v1", "test-key")
    if kind in {"success", "server-retry"}:
        result = await provider.generate(request_data)
        assert result.output.summary == "A safe summary"
        assert result.input_tokens == 4
        assert calls[0]["json"]["response_format"]["type"] == "json_schema"
    else:
        with pytest.raises((ProviderFailure, ValueError, ValidationError)):
            await provider.generate(request_data)
    assert len(calls) == (3 if kind in {"timeout", "server-retry"} else 1)


@pytest.mark.parametrize(
    "payload",
    [
        {"task_type": "execute_sql", "input": {"text": "select 1"}},
        {"task_type": "summarize_text", "input": {"text": "x" * 12001}},
        {"task_type": "summarize_text", "input": {"text": ""}},
        {"task_type": "summarize_text", "input": {"text": "safe"}, "tools": ["shell"]},
    ],
)
def test_gateway_input_limits(payload):
    with pytest.raises(ValidationError):
        ExecuteRequest(**payload)
