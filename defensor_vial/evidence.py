"""Bóveda de evidencia ("caja negra") de Defensor Vial MX — Fase 3.

Permite que el usuario documente una detención guardando fotos, videos, audios,
documentos y su ubicación, cada uno con un **sello de tiempo** y metadatos. El
objetivo es darle al ciudadano un expediente fechado e íntegro que respalde una
detención abusiva.

Diseño deliberado: esta clase NO habla con Telegram ni con la red. Recibe los
bytes ya descargados y los persiste; así el bot se encarga de la red y este
módulo queda completamente probable sin credenciales (igual que el resto del
proyecto). El almacenamiento es por usuario:

    <evidence_dir>/<user_id>/index.json      ← metadatos (orden y sellos de tiempo)
    <evidence_dir>/<user_id>/0001_foto.jpg   ← archivos de evidencia
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

# Tipos de evidencia reconocidos (etiqueta legible que se usa en el acta).
KIND_FOTO = "foto"
KIND_VIDEO = "video"
KIND_AUDIO = "audio"
KIND_DOCUMENTO = "documento"
KIND_UBICACION = "ubicacion"
KIND_NOTA = "nota"

# Extensión por defecto cuando Telegram no nos da una clara.
_DEFAULT_EXT = {
    KIND_FOTO: ".jpg",
    KIND_VIDEO: ".mp4",
    KIND_AUDIO: ".ogg",
    KIND_DOCUMENTO: ".bin",
}


@dataclass
class EvidenceItem:
    """Un elemento del expediente, con su sello de tiempo."""

    seq: int  # número consecutivo dentro del expediente del usuario
    kind: str  # foto | video | audio | documento | ubicacion | nota
    created_at: str  # ISO 8601 local, p. ej. "2026-06-07T14:32:05"
    filename: str | None = None  # ruta relativa al directorio del usuario
    caption: str | None = None  # texto que acompañó al archivo
    lat: float | None = None
    lon: float | None = None
    note: str | None = None  # texto de una nota libre

    def when(self) -> str:
        """Sello de tiempo legible (dd/mm/aaaa HH:MM)."""
        try:
            dt = datetime.fromisoformat(self.created_at)
            return dt.strftime("%d/%m/%Y %H:%M hrs")
        except ValueError:
            return self.created_at

    def describe(self) -> str:
        """Descripción de una línea para listados y el acta."""
        if self.kind == KIND_UBICACION:
            return f"Ubicación ({self.lat:.5f}, {self.lon:.5f})"
        if self.kind == KIND_NOTA:
            texto = (self.note or "").strip().replace("\n", " ")
            corto = texto[:80] + ("…" if len(texto) > 80 else "")
            return f"Nota: {corto}"
        etiqueta = self.kind.capitalize()
        if self.caption:
            cap = self.caption.strip().replace("\n", " ")
            cap = cap[:60] + ("…" if len(cap) > 60 else "")
            return f"{etiqueta} — “{cap}”"
        return etiqueta

    def maps_url(self) -> str | None:
        if self.lat is None or self.lon is None:
            return None
        return f"https://maps.google.com/?q={self.lat},{self.lon}"


def _sanitize_user_id(user_id: str) -> str:
    """Evita rutas inesperadas a partir de un identificador de usuario."""
    safe = "".join(c for c in str(user_id) if c.isalnum() or c in {"-", "_"})
    return safe or "anon"


class EvidenceVault:
    """Almacén de evidencia por usuario, con índice persistente en JSON."""

    def __init__(
        self,
        base_dir: Path | str,
        clock: Callable[[], datetime] | None = None,
    ):
        self.base_dir = Path(base_dir)
        # Reloj inyectable: facilita pruebas deterministas.
        self._now = clock or datetime.now

    # --- Rutas e índice ---

    def _user_dir(self, user_id: str) -> Path:
        d = self.base_dir / _sanitize_user_id(user_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _index_path(self, user_id: str) -> Path:
        return self._user_dir(user_id) / "index.json"

    def _load(self, user_id: str) -> list[EvidenceItem]:
        path = self._index_path(user_id)
        if not path.exists():
            return []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        items: list[EvidenceItem] = []
        for d in raw:
            # Tolerante a campos extra/faltantes para no romper con datos viejos.
            campos = {k: d.get(k) for k in EvidenceItem.__dataclass_fields__}
            items.append(EvidenceItem(**campos))
        return items

    def _save(self, user_id: str, items: list[EvidenceItem]) -> None:
        path = self._index_path(user_id)
        data = [asdict(it) for it in items]
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _next_seq(self, items: list[EvidenceItem]) -> int:
        return (max((it.seq for it in items), default=0)) + 1

    # --- Altas ---

    def add_file(
        self,
        user_id: str,
        kind: str,
        data: bytes,
        ext: str | None = None,
        caption: str | None = None,
    ) -> EvidenceItem:
        """Guarda un archivo binario (foto/video/audio/documento) con su sello."""
        items = self._load(user_id)
        seq = self._next_seq(items)
        ext = _normalize_ext(ext) or _DEFAULT_EXT.get(kind, ".bin")
        filename = f"{seq:04d}_{kind}{ext}"
        (self._user_dir(user_id) / filename).write_bytes(data)
        item = EvidenceItem(
            seq=seq,
            kind=kind,
            created_at=self._now().isoformat(timespec="seconds"),
            filename=filename,
            caption=caption,
        )
        items.append(item)
        self._save(user_id, items)
        return item

    def add_location(self, user_id: str, lat: float, lon: float) -> EvidenceItem:
        items = self._load(user_id)
        seq = self._next_seq(items)
        item = EvidenceItem(
            seq=seq,
            kind=KIND_UBICACION,
            created_at=self._now().isoformat(timespec="seconds"),
            lat=float(lat),
            lon=float(lon),
        )
        items.append(item)
        self._save(user_id, items)
        return item

    def add_note(self, user_id: str, text: str) -> EvidenceItem:
        items = self._load(user_id)
        seq = self._next_seq(items)
        item = EvidenceItem(
            seq=seq,
            kind=KIND_NOTA,
            created_at=self._now().isoformat(timespec="seconds"),
            note=text,
        )
        items.append(item)
        self._save(user_id, items)
        return item

    # --- Consulta y limpieza ---

    def items(self, user_id: str) -> list[EvidenceItem]:
        return self._load(user_id)

    def count(self, user_id: str) -> int:
        return len(self._load(user_id))

    def latest(self, user_id: str, kind: str) -> EvidenceItem | None:
        """Devuelve el elemento más reciente de un tipo dado (o None)."""
        for it in reversed(self._load(user_id)):
            if it.kind == kind:
                return it
        return None

    def file_bytes(self, user_id: str, item: EvidenceItem) -> bytes | None:
        """Lee los bytes del archivo asociado a un elemento (o None)."""
        if not item.filename:
            return None
        path = self._user_dir(user_id) / item.filename
        return path.read_bytes() if path.exists() else None

    def clear(self, user_id: str) -> int:
        """Elimina todo el expediente del usuario. Devuelve cuántos había."""
        items = self._load(user_id)
        user_dir = self._user_dir(user_id)
        for it in items:
            if it.filename:
                f = user_dir / it.filename
                if f.exists():
                    f.unlink()
        idx = self._index_path(user_id)
        if idx.exists():
            idx.unlink()
        return len(items)

    # --- Acta / reporte ---

    def build_acta(
        self,
        user_id: str,
        *,
        estado: str | None = None,
        vehiculo: str | None = None,
        argumentos: str | None = None,
    ) -> str:
        """Genera el acta del expediente como texto (Markdown de Telegram)."""
        items = self._load(user_id)
        ahora = self._now().strftime("%d/%m/%Y %H:%M hrs")
        lineas: list[str] = []
        lineas.append("📋 *ACTA DE HECHOS — Defensor Vial MX*")
        lineas.append(f"_Generada el {ahora}_\n")

        ctx: list[str] = []
        if estado:
            ctx.append(f"*Lugar:* {estado}")
        if vehiculo:
            ctx.append(f"*Vehículo:* {vehiculo}")
        if ctx:
            lineas.append("  •  ".join(ctx) + "\n")

        if not items:
            lineas.append(
                "Aún no has registrado evidencia. Envíame fotos, video, audio "
                "o tu ubicación y los guardaré con su fecha y hora."
            )
            return "\n".join(lineas)

        lineas.append(f"*Evidencias registradas:* {len(items)}\n")
        for it in items:
            linea = f"{it.seq}. 🕒 {it.when()} — {it.describe()}"
            url = it.maps_url()
            if url:
                linea += f"\n   📍 {url}"
            lineas.append(linea)

        if argumentos:
            lineas.append("\n*Argumentos legales aplicables:*")
            lineas.append(argumentos.strip())

        lineas.append(
            "\n⚠️ Documento informativo generado automáticamente; no "
            "sustituye un acta ministerial ni la asesoría de un abogado. Los "
            "archivos quedan guardados con su sello de tiempo."
        )
        return "\n".join(lineas)


def _normalize_ext(ext: str | None) -> str | None:
    """Normaliza una extensión a la forma '.xxx' en minúsculas."""
    if not ext:
        return None
    ext = ext.strip().lower()
    if not ext:
        return None
    if not ext.startswith("."):
        ext = "." + ext
    # Evita extensiones absurdas o con separadores de ruta.
    if "/" in ext or "\\" in ext or len(ext) > 8:
        return None
    return ext
