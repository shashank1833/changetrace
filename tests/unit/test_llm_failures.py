import json

import httpx
import pytest
from changetrace_schemas import ChangeIntent
from pydantic import ValidationError

from services.llm.client import MockLLMClient, OpenAICompatibleClient


@pytest.mark.parametrize(
    "response",
    [
        {"entities": "not-a-list"},
        {
            "entities": [],
            "actions": [],
            "states_added": [],
            "states_removed": [],
            "constraints": [],
            "expected_behaviors": [],
            "extra": "forbidden",
        },
    ],
)
def test_mock_llm_rejects_schema_invalid_output(response):
    with pytest.raises(ValidationError):
        MockLLMClient({"intent": response}).structured(purpose="intent", prompt="untrusted", output_schema=ChangeIntent)


def test_mock_llm_missing_response_fails_closed():
    with pytest.raises(RuntimeError, match="No mock response"):
        MockLLMClient({}).structured(purpose="intent", prompt="untrusted", output_schema=ChangeIntent)


def test_provider_malformed_json_retries_then_fails(monkeypatch):
    calls = 0

    def fake_post(*args, **kwargs):
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            request=httpx.Request("POST", "https://llm.invalid/chat/completions"),
            json={"choices": [{"message": {"content": "not-json"}}]},
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    client = OpenAICompatibleClient("https://llm.invalid", "secret", "model")
    with pytest.raises(RuntimeError, match="Structured model call failed"):
        client.structured(purpose="intent", prompt="data", output_schema=ChangeIntent)
    assert calls == 2


def test_provider_rejects_fabricated_component_and_oversized_output(monkeypatch):
    huge = json.dumps({"entities": ["x" * 100_000]})

    def fake_post(*args, **kwargs):
        return httpx.Response(
            200,
            request=httpx.Request("POST", "https://llm.invalid/chat/completions"),
            json={"choices": [{"message": {"content": huge}}]},
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    client = OpenAICompatibleClient("https://llm.invalid", "secret", "model")
    with pytest.raises(RuntimeError, match="Structured model call failed"):
        client.structured(purpose="intent", prompt="data", output_schema=ChangeIntent)


def test_provider_valid_json_is_schema_validated(monkeypatch):
    payload = {
        "entities": ["ticket"],
        "actions": ["close"],
        "states_added": [],
        "states_removed": [],
        "constraints": [],
        "expected_behaviors": ["close ticket"],
    }

    def fake_post(*args, **kwargs):
        return httpx.Response(
            200,
            request=httpx.Request("POST", "https://llm.invalid/chat/completions"),
            json={"choices": [{"message": {"content": json.dumps(payload)}}], "usage": {"prompt_tokens": 2}},
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    result, metadata = OpenAICompatibleClient("https://llm.invalid", "secret", "model").structured(
        purpose="intent", prompt="data", output_schema=ChangeIntent
    )
    assert result.entities == ["ticket"]
    assert metadata.prompt_tokens == 2
