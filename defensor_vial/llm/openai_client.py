"""Cliente de OpenAI Chat Completions usando solo la librería estándar.

Se evita el SDK oficial para no depender de paquetes con extensiones
compiladas (pydantic-core), lo que maximiza la compatibilidad con versiones
muy recientes de Python (3.14) en Windows. La comunicación es vía
``urllib.request`` contra el endpoint ``/chat/completions``.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .base import LLMError, Message


class OpenAIClient:
    """Cliente mínimo de Chat Completions de OpenAI."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        temperature: float = 0.2,
        timeout: int = 60,
        vision_model: str | None = None,
    ):
        self.api_key = api_key
        self.model = model
        # gpt-4o-mini ya soporta visión; se permite un modelo distinto si se desea.
        self.vision_model = vision_model or model
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.timeout = timeout

    def complete(self, messages: list[Message]) -> str:
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [m.as_dict() for m in messages],
        }
        return self._post(payload)

    def analyze_image(
        self,
        system_prompt: str,
        user_prompt: str,
        image_b64: str,
        mime: str = "image/jpeg",
    ) -> str:
        """Analiza una imagen (visión) y devuelve el texto del modelo.

        Usa el formato multimodal de Chat Completions: el contenido del mensaje
        de usuario es una lista con un bloque de texto y un bloque de imagen
        codificada como data URI en base64.
        """
        data_uri = f"data:{mime};base64,{image_b64}"
        payload = {
            "model": self.vision_model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                },
            ],
        }
        return self._post(payload)

    def _post(self, payload: dict) -> str:
        """Envía una petición a /chat/completions y devuelve el contenido."""
        if not self.api_key:
            raise LLMError(
                "No hay OPENAI_API_KEY configurada; no es posible generar la "
                "respuesta. Configúrala en el archivo .env."
            )

        url = f"{self.base_url}/chat/completions"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:  # respuesta con código de error
            detail = exc.read().decode("utf-8", errors="replace")
            raise LLMError(
                f"OpenAI respondió {exc.code}: {detail[:500]}"
            ) from exc
        except urllib.error.URLError as exc:  # error de red / conexión
            raise LLMError(f"No se pudo conectar con OpenAI: {exc.reason}") from exc

        try:
            parsed = json.loads(body)
            return parsed["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise LLMError(
                f"Respuesta inesperada de OpenAI: {body[:500]}"
            ) from exc
