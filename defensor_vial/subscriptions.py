"""Padrón de suscriptores de Defensor Vial MX — control de acceso de paga.

El bot es un único servicio para todos los clientes: Telegram ya separa a cada
persona por su ``user_id``. Este módulo añade lo único que faltaba para cobrar:
una **lista de quién está al corriente** y hasta qué fecha.

Diseño deliberado (igual que el resto del proyecto):
- NO toca la red ni cobra dinero. El pago es externo (efectivo, transferencia,
  lo que sea) y el dueño activa al cliente A MANO con ``/activar``.
- Persistencia en un solo archivo JSON, legible y editable a mano:

    <subscriptions_db>   ← p. ej. evidence/_subscriptions.json

  Estructura: { "<user_id>": {datos del suscriptor}, ... }
- Reloj inyectable para pruebas deterministas (igual que la bóveda de evidencia).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable


@dataclass
class Subscriber:
    """Un cliente del padrón, con su fecha de vencimiento."""

    user_id: str
    name: str | None = None
    plan: str = "mensual"
    activated_at: str = ""  # ISO datetime de la PRIMERA alta
    expires_at: str = ""  # fecha ISO "YYYY-MM-DD" (vigente hasta ese día incluido)
    notes: str | None = None

    def expiry_date(self) -> date | None:
        try:
            return date.fromisoformat(self.expires_at)
        except (ValueError, TypeError):
            return None

    def expires_human(self) -> str:
        d = self.expiry_date()
        return d.strftime("%d/%m/%Y") if d else "—"


def _coerce(raw: dict) -> Subscriber:
    """Crea un Subscriber tolerando claves desconocidas o faltantes."""
    known = {f.name for f in fields(Subscriber)}
    data = {k: v for k, v in raw.items() if k in known}
    return Subscriber(**data)


class SubscriptionStore:
    """Padrón persistente de suscriptores en un archivo JSON."""

    def __init__(
        self,
        path: str | Path,
        clock: Callable[[], datetime] | None = None,
    ):
        self.path = Path(path)
        self._now = clock or datetime.now
        self._subs: dict[str, Subscriber] = {}
        self._load()

    # --- Persistencia ---

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            raw = {}
        if isinstance(raw, dict):
            for uid, data in raw.items():
                if isinstance(data, dict):
                    self._subs[str(uid)] = _coerce({**data, "user_id": str(uid)})

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {uid: asdict(sub) for uid, sub in self._subs.items()}
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp.replace(self.path)

    # --- Consultas ---

    def today(self) -> date:
        return self._now().date()

    def get(self, user_id: str) -> Subscriber | None:
        return self._subs.get(str(user_id))

    def is_active(self, user_id: str) -> bool:
        sub = self._subs.get(str(user_id))
        if sub is None:
            return False
        d = sub.expiry_date()
        return bool(d and self.today() <= d)

    def all(self) -> list[Subscriber]:
        """Suscriptores ordenados por fecha de vencimiento (más próxima primero)."""
        return sorted(
            self._subs.values(),
            key=lambda s: (s.expiry_date() or date.max),
        )

    # --- Altas y bajas (las usa el administrador) ---

    def activate(
        self,
        user_id: str,
        days: int = 30,
        name: str | None = None,
        plan: str | None = None,
        notes: str | None = None,
    ) -> Subscriber:
        """Da de alta o RENUEVA a un cliente por ``days`` días.

        Si el cliente ya está vigente, los días se SUMAN a su vencimiento actual
        (no se pierde tiempo ya pagado). Si está vencido o es nuevo, cuenta desde
        hoy. Conserva la fecha de la primera alta.
        """
        uid = str(user_id)
        existing = self._subs.get(uid)
        if existing and self.is_active(uid):
            base = existing.expiry_date() or self.today()
        else:
            base = self.today()
        new_expiry = base + timedelta(days=days)

        activated_at = (
            existing.activated_at
            if existing and existing.activated_at
            else self._now().isoformat(timespec="seconds")
        )
        sub = Subscriber(
            user_id=uid,
            name=name if name is not None else (existing.name if existing else None),
            plan=plan or (existing.plan if existing else "mensual"),
            activated_at=activated_at,
            expires_at=new_expiry.isoformat(),
            notes=notes if notes is not None else (existing.notes if existing else None),
        )
        self._subs[uid] = sub
        self._save()
        return sub

    def deactivate(self, user_id: str) -> bool:
        """Elimina a un cliente del padrón. Devuelve True si existía."""
        uid = str(user_id)
        if uid in self._subs:
            del self._subs[uid]
            self._save()
            return True
        return False
