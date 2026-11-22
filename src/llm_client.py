"""LLM port and the single fixed local Spark client."""

from __future__ import annotations

import json
from typing import Protocol, runtime_checkable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import requests

from .config import (
    BASE_URL,
    ENABLE_THINKING,
    MAX_TOKENS,
    MODEL_ID,
    REPEAT_PENALTY,
    REQUEST_TIMEOUT_SECONDS,
    TEMPERATURE,
    TOP_K,
    TOP_P,
)
from .domain import GenerationError


@runtime_checkable
class LLMPort(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class LlamaServerClient:
    """Calls one fixed llama-server URL. No configurable host (no SSRF)."""

    def __init__(self, base_url: str = BASE_URL, model: str = MODEL_ID) -> None:
        self.base_url = base_url
        self.model = model

    def complete(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": TEMPERATURE,
            "top_p": TOP_P,
            "top_k": TOP_K,
            "repeat_penalty": REPEAT_PENALTY,
            "max_tokens": MAX_TOKENS,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": ENABLE_THINKING},
        }
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            envelope = response.json()
            content = envelope["choices"][0]["message"]["content"]
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError) as exc:
            raise GenerationError(f"Local Spark call failed: {type(exc).__name__}") from exc
        if not isinstance(content, str) or not content.strip():
            raise GenerationError("Local Spark returned an empty response.")
        return content


class OpenAICompatProbe:
    """Health/readiness probe. No generation, no user text."""

    def __init__(self, base_url: str = BASE_URL) -> None:
        self.base_url = base_url

    def models(self) -> list[str]:
        try:
            with urlopen(f"{self.base_url}/models", timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return [m.get("id", "") for m in payload.get("data", [])]
        except (HTTPError, URLError, TimeoutError, ValueError, AttributeError) as exc:
            raise GenerationError(f"Spark endpoint unreachable: {type(exc).__name__}") from exc
