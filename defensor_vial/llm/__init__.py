"""Capa de generación de lenguaje (LLM) con proveedor conectable.

Fase 1 incluye un proveedor: OpenAI (``OpenAIClient``). La interfaz
:class:`LLMClient` permite añadir otros proveedores (Anthropic, local, etc.)
en fases posteriores sin tocar el resto del sistema.
"""

from .base import LLMClient, LLMError, Message, VisionLLMClient
from .openai_client import OpenAIClient

__all__ = [
    "LLMClient",
    "VisionLLMClient",
    "LLMError",
    "Message",
    "OpenAIClient",
    "build_llm",
]


def build_llm(config) -> LLMClient:
    """Crea el cliente de LLM según la configuración (fábrica)."""
    provider = config.llm_provider
    if provider == "openai":
        return OpenAIClient(
            api_key=config.openai_api_key,
            model=config.openai_model,
            base_url=config.openai_base_url,
            temperature=config.llm_temperature,
            timeout=config.llm_timeout,
            vision_model=config.openai_vision_model,
        )
    raise LLMError(f"Proveedor de LLM no soportado: {provider!r}")
