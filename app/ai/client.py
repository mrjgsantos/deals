from __future__ import annotations

from abc import ABC, abstractmethod

from app.core.config import settings

_STUB_MODEL = "stub-model"


class ModelClient(ABC):
    @abstractmethod
    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError


class StubModelClient(ModelClient):
    def __init__(self, response_text: str) -> None:
        self.response_text = response_text

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        return self.response_text


class AnthropicModelClient(ModelClient):
    def __init__(self, model_name: str) -> None:
        import anthropic

        self._client = anthropic.Anthropic()
        self._model = model_name

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        message = self._client.messages.create(
            model=self._model,
            max_tokens=256,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return message.content[0].text


def build_model_client_from_env() -> ModelClient:
    if settings.ai_copy_model_name and settings.ai_copy_model_name != _STUB_MODEL:
        return AnthropicModelClient(settings.ai_copy_model_name)
    return StubModelClient(settings.ai_copy_stub_response)
