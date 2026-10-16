"""The language-model interface.

Everything else depends only on the LanguageModel protocol. OpenAICompatibleLLM speaks the
OpenAI chat-completions API, which both Ollama (local, used now) and Azure OpenAI (if IT approves
it) provide - so switching provider is a configuration change, not a code change. Tests use a
scripted fake instead of a real model.
"""

from dataclasses import dataclass
from typing import Any, Protocol

import openai

from mypal.config import Settings


@dataclass(frozen=True)
class LLMReply:
    content: str
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None


class GenerationUnavailable(RuntimeError):
    """The model could not be reached or did not respond in time."""


class LanguageModel(Protocol):
    @property
    def model_name(self) -> str: ...

    def complete_json(
        self, system: str, user: str, schema_name: str, schema: dict[str, Any]
    ) -> LLMReply: ...


class OpenAICompatibleLLM:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None,
        timeout_seconds: float,
        disable_reasoning: bool,
    ) -> None:
        # Ollama ignores the key, but the client library requires a value.
        self._client = openai.OpenAI(
            base_url=base_url, api_key=api_key or "not-needed", timeout=timeout_seconds
        )
        self._model = model
        self._disable_reasoning = disable_reasoning

    @property
    def model_name(self) -> str:
        return self._model

    def complete_json(
        self, system: str, user: str, schema_name: str, schema: dict[str, Any]
    ) -> LLMReply:
        extra: dict[str, Any] = {"reasoning_effort": "none"} if self._disable_reasoning else {}
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                # Same question and evidence -> as consistent an answer as possible.
                temperature=0,
                # Constrains the output to valid JSON matching the schema.
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": schema_name, "schema": schema, "strict": True},
                },
                **extra,
            )
        except openai.OpenAIError as exc:
            raise GenerationUnavailable(f"{type(exc).__name__}: {exc}") from exc

        usage = response.usage
        return LLMReply(
            content=response.choices[0].message.content or "",
            model=response.model or self._model,
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
        )


def create_llm(settings: Settings) -> LanguageModel:
    return OpenAICompatibleLLM(
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        api_key=settings.llm_api_key.get_secret_value() if settings.llm_api_key else None,
        timeout_seconds=settings.llm_timeout_seconds,
        disable_reasoning=settings.llm_disable_reasoning,
    )
