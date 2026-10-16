"""Test doubles for the embedding model and the language model.

They make tests fast, deterministic and independent of Ollama - while Postgres and Qdrant stay
real, because the security filtering must be tested against the real systems.
"""

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any

from mypal.answering.llm import GenerationUnavailable, LLMReply


class HashEmbedder:
    """Bag-of-words vectors: texts sharing words get similar vectors, texts sharing none get a
    similarity near 0. Crude, but predictable - exactly what retrieval tests need."""

    model_name = "test-hash-embedder"
    dimension = 256

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            bucket = int(hashlib.sha256(word.encode()).hexdigest(), 16) % self.dimension
            vector[bucket] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


@dataclass
class ScriptedLLM:
    """Returns pre-written replies and records every prompt it was given."""

    replies: list[dict[str, Any] | str] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)
    model_name: str = "scripted-test-model"

    def complete_json(
        self, system: str, user: str, schema_name: str, schema: dict[str, Any]
    ) -> LLMReply:
        self.prompts.append(user)
        reply = self.replies.pop(0) if self.replies else {}
        content = reply if isinstance(reply, str) else json.dumps(reply)
        return LLMReply(content, self.model_name, prompt_tokens=100, completion_tokens=20)

    @property
    def calls(self) -> int:
        return len(self.prompts)


class UnavailableLLM:
    model_name = "unavailable-test-model"

    def complete_json(self, *args: object) -> LLMReply:
        raise GenerationUnavailable("connection refused")


def answer(text: str, *citations: str) -> dict[str, Any]:
    return {"answer": text, "citations": list(citations), "clarification_question": ""}
