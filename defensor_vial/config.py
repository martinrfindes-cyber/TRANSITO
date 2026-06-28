"""Configuración central de Defensor Vial MX.

Toda la configuración se lee de variables de entorno (ver ``.env.example``).
Se evita acoplar el resto del código a ``os.environ`` para facilitar pruebas.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Carga opcional de un archivo .env si python-dotenv está instalado.
# No es obligatorio: el sistema funciona con variables de entorno normales.
try:  # pragma: no cover - dependencia opcional
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass


# Raíz del repositorio (carpeta que contiene este paquete).
ROOT_DIR = Path(__file__).resolve().parent.parent


def _get_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "si", "sí", "on"}


def _get_int(name: str, default: int) -> int:
    val = os.getenv(name)
    if val is None or not val.strip():
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    val = os.getenv(name)
    if val is None or not val.strip():
        return default
    try:
        return float(val)
    except ValueError:
        return default


def _get_ids(name: str) -> frozenset[str]:
    """Lee una lista de IDs de Telegram separados por coma, espacio o punto y coma."""
    raw = os.getenv(name, "")
    partes = raw.replace(";", ",").replace(" ", ",").split(",")
    return frozenset(p.strip() for p in partes if p.strip())


@dataclass
class Config:
    """Parámetros de ejecución del asistente."""

    # --- Telegram ---
    telegram_bot_token: str = field(
        default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    )

    # --- Proveedor de LLM ---
    # Proveedor activo para la generación de texto. Conectable: "openai" (def.).
    llm_provider: str = field(
        default_factory=lambda: os.getenv("LLM_PROVIDER", "openai").strip().lower()
    )
    openai_api_key: str = field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY", "").strip()
    )
    openai_model: str = field(
        default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
    )
    # Modelo para análisis de imágenes (boletas). gpt-4o-mini ya soporta visión.
    openai_vision_model: str = field(
        default_factory=lambda: os.getenv(
            "OPENAI_VISION_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        ).strip()
    )
    openai_base_url: str = field(
        default_factory=lambda: os.getenv(
            "OPENAI_BASE_URL", "https://api.openai.com/v1"
        ).strip().rstrip("/")
    )
    llm_temperature: float = field(
        default_factory=lambda: _get_float("LLM_TEMPERATURE", 0.2)
    )
    llm_timeout: int = field(default_factory=lambda: _get_int("LLM_TIMEOUT", 60))

    # --- Base de conocimiento / RAG ---
    knowledge_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv("KNOWLEDGE_DIR", str(ROOT_DIR / "knowledge"))
        ).expanduser()
    )
    top_k: int = field(default_factory=lambda: _get_int("RAG_TOP_K", 6))
    # Puntaje mínimo (BM25 normalizado) para considerar que hay evidencia útil.
    min_score: float = field(default_factory=lambda: _get_float("RAG_MIN_SCORE", 0.05))

    # --- Historial de conversación ---
    history_max_turns: int = field(
        default_factory=lambda: _get_int("HISTORY_MAX_TURNS", 8)
    )

    # --- Bóveda de evidencia (Fase 3) ---
    evidence_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv("EVIDENCE_DIR", str(ROOT_DIR / "evidence"))
        ).expanduser()
    )
    # Tamaño máximo por archivo a descargar de Telegram (MB). 0 = sin límite.
    evidence_max_mb: int = field(
        default_factory=lambda: _get_int("EVIDENCE_MAX_MB", 20)
    )

    # --- Suscripciones (control de acceso de paga) ---
    # IDs de Telegram con permisos de administrador (pueden activar clientes).
    admin_ids: frozenset[str] = field(default_factory=lambda: _get_ids("ADMIN_IDS"))
    # Si es True, solo responden los user_id activos en el padrón (y los admins).
    # Si es False (def.), el bot atiende a todos como antes (modo abierto/demo).
    require_subscription: bool = field(
        default_factory=lambda: _get_bool("REQUIRE_SUBSCRIPTION", False)
    )
    # Días que dura una activación con /activar cuando no se indican días.
    subscription_days: int = field(
        default_factory=lambda: _get_int("SUBSCRIPTION_DAYS", 30)
    )
    # Ruta del padrón JSON. Por defecto vive dentro de evidence/ para que persista
    # con el mismo volumen montado en producción (un solo mount basta para ambos).
    subscriptions_db: Path | None = field(
        default_factory=lambda: (
            Path(os.environ["SUBSCRIPTIONS_DB"]).expanduser()
            if os.getenv("SUBSCRIPTIONS_DB", "").strip()
            else None
        )
    )

    def __post_init__(self) -> None:
        if self.subscriptions_db is None:
            self.subscriptions_db = self.evidence_dir / "_subscriptions.json"

    def validate_for_bot(self) -> list[str]:
        """Devuelve la lista de problemas que impedirían arrancar el bot."""
        problems: list[str] = []
        if not self.telegram_bot_token:
            problems.append("Falta TELEGRAM_BOT_TOKEN (token del bot de Telegram).")
        problems.extend(self.validate_for_llm())
        if not self.knowledge_dir.exists():
            problems.append(
                f"No existe la carpeta de conocimiento: {self.knowledge_dir}"
            )
        if self.require_subscription and not self.admin_ids:
            problems.append(
                "REQUIRE_SUBSCRIPTION está activo pero ADMIN_IDS está vacío: "
                "nadie podría activar clientes y el servicio quedaría bloqueado. "
                "Define ADMIN_IDS con tu user_id de Telegram."
            )
        return problems

    def validate_for_llm(self) -> list[str]:
        """Problemas que impedirían generar respuestas con el LLM."""
        problems: list[str] = []
        if self.llm_provider == "openai":
            if not self.openai_api_key:
                problems.append(
                    "Falta OPENAI_API_KEY (clave de la API de OpenAI)."
                )
        else:
            problems.append(
                f"Proveedor de LLM no soportado en Fase 1: {self.llm_provider!r}"
            )
        return problems


def load_config() -> Config:
    """Construye la configuración a partir del entorno."""
    return Config()
