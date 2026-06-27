"""Historial de conversación y estado de sesión por usuario (en memoria).

Fase 1: almacenamiento en memoria del proceso. Es suficiente para el MVP y
mantiene la arquitectura simple. En fases posteriores puede sustituirse por un
backend persistente (SQLite/Redis) sin cambiar la interfaz pública.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from .llm.base import Message


@dataclass
class Session:
    """Estado conversacional de un usuario."""

    user_id: str
    estado: str | None = None  # CDMX | EDOMEX
    vehiculo: str | None = None  # automovil | motocicleta
    turns: deque[Message] = field(default_factory=lambda: deque(maxlen=16))

    def add(self, role: str, content: str) -> None:
        self.turns.append(Message(role=role, content=content))

    def recent(self, max_turns: int) -> list[Message]:
        """Devuelve los últimos ``max_turns`` mensajes (pares u-a)."""
        items = list(self.turns)
        return items[-max_turns:] if max_turns > 0 else items

    def reset(self) -> None:
        self.estado = None
        self.vehiculo = None
        self.turns.clear()


class SessionStore:
    """Repositorio de sesiones por ``user_id``."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def get(self, user_id: str) -> Session:
        if user_id not in self._sessions:
            self._sessions[user_id] = Session(user_id=user_id)
        return self._sessions[user_id]

    def reset(self, user_id: str) -> None:
        self.get(user_id).reset()
