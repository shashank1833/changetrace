from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TypeVar

import httpx
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class LLMMetadata:
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LLMClient(ABC):
    @abstractmethod
    def structured(self, *, purpose: str, prompt: str, output_schema: type[T]) -> tuple[T, LLMMetadata]:
        """Return validated structured output. Implementations must not log prompt content."""


class OpenAICompatibleClient(LLMClient):
    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 30):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def structured(self, *, purpose: str, prompt: str, output_schema: type[T]) -> tuple[T, LLMMetadata]:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": purpose}, {"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        error: Exception | None = None
        for _attempt in range(2):
            try:
                response = httpx.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=payload,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                body = response.json()
                content = body["choices"][0]["message"]["content"]
                if not isinstance(content, str) or len(content.encode("utf-8")) > 64_000:
                    raise ValueError("Structured model output exceeds the validation limit")
                parsed = output_schema.model_validate(json.loads(content))
                usage = body.get("usage", {})
                return parsed, LLMMetadata(
                    "openai-compatible", self.model, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
                )
            except (httpx.HTTPError, KeyError, json.JSONDecodeError, ValueError) as exc:
                error = exc
        raise RuntimeError(f"Structured model call failed for {purpose}") from error


class MockLLMClient(LLMClient):
    def __init__(self, responses: dict[str, dict]):
        self.responses = responses

    def structured(self, *, purpose: str, prompt: str, output_schema: type[T]) -> tuple[T, LLMMetadata]:
        if purpose not in self.responses:
            raise RuntimeError(f"No mock response for {purpose}")
        return output_schema.model_validate(self.responses[purpose]), LLMMetadata("mock", "mock-v1")
