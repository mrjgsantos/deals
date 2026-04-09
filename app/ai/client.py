from __future__ import annotations

from abc import ABC, abstractmethod

from app.core.config import settings


class ModelClient(ABC):
    @abstractmethod
    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError


class StubModelClient(ModelClient):
    def __init__(self, response_text: str) -> None:
        self.response_text = response_text

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        return self.response_text


def build_model_client_from_env() -> ModelClient:
    return StubModelClient(settings.ai_copy_stub_response)
