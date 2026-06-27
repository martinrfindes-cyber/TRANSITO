"""Interfaz común para proveedores de LLM."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class LLMError(RuntimeError):
    """Error al invocar el proveedor de LLM."""


@dataclass
class Message:
    """Mensaje de chat (role: 'system' | 'user' | 'assistant')."""

    role: str
    content: str

    def as_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


class LLMClient(Protocol):
    """Contrato mínimo que debe cumplir un proveedor de LLM."""

    def complete(self, messages: list[Message]) -> str:
        """Genera una respuesta de texto a partir de una lista de mensajes."""
        ...


class VisionLLMClient(Protocol):
    """Contrato para proveedores con capacidad de análisis de imágenes."""

    def analyze_image(
        self,
        system_prompt: str,
        user_prompt: str,
        image_b64: str,
        mime: str = "image/jpeg",
    ) -> str:
        """Analiza una imagen y devuelve la respuesta del modelo en texto."""
        ...
