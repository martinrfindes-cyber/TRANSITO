"""Cliente de Telegram (long polling) usando solo la librería estándar.

Consume directamente la API oficial del Bot de Telegram
(https://core.telegram.org/bots/api) mediante ``urllib``. Se evita una
dependencia externa para maximizar la estabilidad y la compatibilidad con
Python 3.14 en Windows.

Comandos:
- /start       : mensaje de bienvenida.
- /help        : ayuda y alcance.
- /reset       : reinicia el historial de conversación (la evidencia se conserva).
- /acta        : genera el acta de hechos con la evidencia registrada.
- /evidencias  : lista la evidencia guardada.
- /borrar      : elimina toda la evidencia del usuario.
Las fotos, videos, audios, documentos y ubicaciones se guardan como evidencia.
Cualquier otro texto se trata como una consulta para el asistente.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from .assistant import Assistant
from .boleta import BoletaAnalyzer, format_report
from .config import Config
from .evidence import (
    KIND_AUDIO,
    KIND_DOCUMENTO,
    KIND_FOTO,
    KIND_VIDEO,
    EvidenceVault,
)
from .llm.base import LLMError

log = logging.getLogger("defensor_vial.bot")

# Límite de longitud de mensaje de Telegram.
_TELEGRAM_MAX = 4096

WELCOME = (
    "👮‍♂️⚖️ *Defensor Vial MX*\n\n"
    "Soy un asistente jurídico especializado en tránsito para *CDMX* y "
    "*Estado de México*. Te ayudo a entender tus derechos y obligaciones "
    "frente a agentes de tránsito y a identificar posibles irregularidades.\n\n"
    "Cuéntame tu situación, por ejemplo:\n"
    "_\"En CDMX un tránsito me quiere multar por polarizado en mi auto\"_\n\n"
    "📸 *Documenta tu detención:* envíame *fotos, video, audio, documentos* o "
    "tu *ubicación* y los guardaré con su fecha y hora como evidencia. Luego "
    "usa /acta para generar tu reporte.\n\n"
    "⚠️ Esta es orientación informativa basada en documentación; no sustituye "
    "la asesoría de un abogado.\n\n"
    "Usa /help para más información o /reset para reiniciar."
)

HELP = (
    "*¿Cómo usarme?*\n\n"
    "1. Describe lo que ocurrió con el mayor detalle posible.\n"
    "2. Indica si fue en *CDMX* o *Estado de México*.\n"
    "3. Indica si conducías un *automóvil* o una *motocicleta*.\n\n"
    "Analizaré tu caso y te daré: resumen, análisis legal, posibles "
    "argumentos de defensa, una respuesta sugerida al agente, el nivel de "
    "riesgo y el fundamento documental utilizado.\n\n"
    "📸 *Evidencia:* manda fotos, video, audio, documentos o tu ubicación "
    "(puedes agregar un texto/caption). Se guardan con sello de tiempo.\n\n"
    "*Alcance actual:* solo CDMX y Estado de México.\n"
    "*Comandos:*\n"
    "/start, /help, /reset\n"
    "/analizar — revisa la foto de tu boleta/multa (datos, requisitos, artículos)\n"
    "/acta — genera tu acta de hechos con la evidencia\n"
    "/evidencias — lista lo que has guardado\n"
    "/borrar — elimina toda tu evidencia"
)


class TelegramBot:
    """Bot de Telegram con long polling sobre la API oficial."""

    def __init__(
        self,
        config: Config,
        assistant: Assistant,
        vault: EvidenceVault | None = None,
    ):
        self.config = config
        self.assistant = assistant
        self.vault = vault or EvidenceVault(config.evidence_dir)
        self.token = config.telegram_bot_token
        self.api = f"https://api.telegram.org/bot{self.token}"
        self.file_api = f"https://api.telegram.org/file/bot{self.token}"
        self._offset: int | None = None
        self._running = False
        self._boleta: BoletaAnalyzer | None = None

    @property
    def boleta(self) -> BoletaAnalyzer:
        # Construcción perezosa: reutiliza el LLM (con visión) y el índice de
        # artículos del asistente. No requiere API key hasta que se usa.
        if self._boleta is None:
            self._boleta = BoletaAnalyzer(
                self.assistant.llm, self.assistant.articles
            )
        return self._boleta

    # --- Llamadas HTTP a la API de Telegram ---

    def _call(self, method: str, params: dict, timeout: int = 65) -> dict:
        url = f"{self.api}/{method}"
        data = urllib.parse.urlencode(params).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_me(self) -> dict:
        return self._call("getMe", {}, timeout=15)

    def send_message(self, chat_id: int, text: str, markdown: bool = True) -> None:
        for chunk in _split_message(text):
            params = {"chat_id": chat_id, "text": chunk}
            if markdown:
                params["parse_mode"] = "Markdown"
            try:
                self._call("sendMessage", params, timeout=20)
            except urllib.error.HTTPError as exc:
                # Si Markdown falla (formato inválido), reintenta sin formato.
                if markdown:
                    log.warning("sendMessage con Markdown falló; reintento plano.")
                    self._call(
                        "sendMessage",
                        {"chat_id": chat_id, "text": chunk},
                        timeout=20,
                    )
                else:
                    raise exc

    def send_typing(self, chat_id: int) -> None:
        try:
            self._call(
                "sendChatAction", {"chat_id": chat_id, "action": "typing"},
                timeout=10,
            )
        except Exception:  # acción no crítica
            pass

    def download_file(self, file_id: str) -> tuple[bytes, str | None]:
        """Descarga un archivo de Telegram. Devuelve (bytes, extensión).

        Usa ``getFile`` para resolver la ruta y luego baja el binario del
        endpoint de archivos. Aplica el límite de tamaño configurado.
        """
        info = self._call("getFile", {"file_id": file_id}, timeout=30)
        if not info.get("ok"):
            raise RuntimeError(f"getFile no OK: {info}")
        file_path = info["result"].get("file_path", "")
        size = info["result"].get("file_size") or 0
        max_bytes = self.config.evidence_max_mb * 1024 * 1024
        if max_bytes and size and size > max_bytes:
            raise ValueError(
                f"archivo demasiado grande ({size // (1024 * 1024)} MB; "
                f"máximo {self.config.evidence_max_mb} MB)"
            )
        url = f"{self.file_api}/{file_path}"
        with urllib.request.urlopen(url, timeout=60) as resp:
            data = resp.read()
        ext = os.path.splitext(file_path)[1] or None
        return data, ext

    # --- Bucle principal ---

    def _get_updates(self) -> list[dict]:
        params = {"timeout": 50}
        if self._offset is not None:
            params["offset"] = self._offset
        try:
            result = self._call("getUpdates", params, timeout=60)
        except urllib.error.URLError as exc:
            log.warning("Error de red en getUpdates: %s", exc)
            time.sleep(3)
            return []
        if not result.get("ok"):
            log.warning("getUpdates no OK: %s", result)
            time.sleep(3)
            return []
        return result.get("result", [])

    def _handle_update(self, update: dict) -> None:
        self._offset = update["update_id"] + 1
        message = update.get("message") or update.get("edited_message")
        if not message:
            return
        chat_id = message["chat"]["id"]
        user_id = str(message["from"]["id"])
        text = (message.get("text") or "").strip()

        # 1. Evidencia adjunta (foto, video, audio, documento, ubicación).
        if self._has_evidence(message):
            self._handle_evidence(chat_id, user_id, message)
            return

        if not text:
            self.send_message(
                chat_id,
                "No reconocí contenido en tu mensaje. Envíame texto para "
                "consultar, o una foto/video/audio/ubicación para guardarlo "
                "como evidencia.",
            )
            return

        # 2. Comandos.
        if text.startswith("/start"):
            self.send_message(chat_id, WELCOME)
            return
        if text.startswith("/help"):
            self.send_message(chat_id, HELP)
            return
        if text.startswith("/reset"):
            self.assistant.reset(user_id)
            n = self.vault.count(user_id)
            extra = f" Tu evidencia ({n}) se conserva." if n else ""
            self.send_message(
                chat_id, f"🔄 Listo, reinicié nuestra conversación.{extra}"
            )
            return
        if text.startswith("/evidencias"):
            self._handle_listar(chat_id, user_id)
            return
        if text.startswith("/acta"):
            self._handle_acta(chat_id, user_id)
            return
        if text.startswith("/analizar"):
            self._handle_analizar(chat_id, user_id)
            return
        if text.startswith("/borrar"):
            n = self.vault.clear(user_id)
            self.send_message(
                chat_id,
                f"🗑️ Eliminé {n} elemento(s) de evidencia."
                if n else "No tenías evidencia guardada.",
            )
            return

        self.send_typing(chat_id)
        try:
            reply = self.assistant.answer(user_id, text)
            self.send_message(chat_id, reply.text)
        except LLMError as exc:
            log.error("Error de LLM: %s", exc)
            self.send_message(
                chat_id,
                "⚠️ No pude generar la respuesta en este momento "
                f"(error del proveedor de IA). Intenta de nuevo más tarde.\n\n_{exc}_",
            )
        except Exception as exc:  # pragma: no cover
            log.exception("Error inesperado procesando mensaje")
            self.send_message(
                chat_id,
                "⚠️ Ocurrió un error inesperado al procesar tu consulta. "
                "Intenta reformularla o usa /reset.",
            )

    # --- Manejo de evidencia ---

    @staticmethod
    def _has_evidence(message: dict) -> bool:
        return any(
            k in message
            for k in ("photo", "video", "voice", "audio", "document", "location")
        )

    def _handle_evidence(self, chat_id: int, user_id: str, message: dict) -> None:
        """Descarga y guarda el contenido adjunto con su sello de tiempo."""
        caption = (message.get("caption") or "").strip() or None

        # Ubicación: no requiere descarga.
        if "location" in message:
            loc = message["location"]
            item = self.vault.add_location(user_id, loc["latitude"], loc["longitude"])
            self.send_message(
                chat_id,
                f"✅ Evidencia {item.seq} guardada — 📍 ubicación, {item.when()}.\n"
                f"{item.maps_url()}\n\nSigue documentando o usa /acta.",
            )
            return

        kind, file_id = self._extract_file(message)
        if not file_id:
            self.send_message(
                chat_id, "No pude identificar el archivo adjunto. Intenta de nuevo."
            )
            return
        try:
            data, ext = self.download_file(file_id)
            item = self.vault.add_file(user_id, kind, data, ext, caption=caption)
        except ValueError as exc:  # tamaño excedido
            self.send_message(chat_id, f"⚠️ No guardé el archivo: {exc}.")
            return
        except Exception:
            log.exception("Error descargando/guardando evidencia")
            self.send_message(
                chat_id,
                "⚠️ Ocurrió un error al guardar tu evidencia. Intenta de nuevo.",
            )
            return
        extra = ""
        if kind == KIND_FOTO:
            extra = (
                "\n📄 Si es una *boleta o multa*, usa /analizar y la reviso por ti."
            )
        self.send_message(
            chat_id,
            f"✅ Evidencia {item.seq} guardada — {item.describe()}, "
            f"{item.when()}.\n\nSigue documentando o usa /acta para tu reporte."
            f"{extra}",
        )

    @staticmethod
    def _extract_file(message: dict) -> tuple[str, str | None]:
        """Devuelve (tipo, file_id) del adjunto soportado más relevante."""
        if "photo" in message and message["photo"]:
            # ``photo`` es una lista de tamaños; el último es el de mayor resolución.
            return KIND_FOTO, message["photo"][-1].get("file_id")
        if "video" in message:
            return KIND_VIDEO, message["video"].get("file_id")
        if "voice" in message:
            return KIND_AUDIO, message["voice"].get("file_id")
        if "audio" in message:
            return KIND_AUDIO, message["audio"].get("file_id")
        if "document" in message:
            return KIND_DOCUMENTO, message["document"].get("file_id")
        return KIND_DOCUMENTO, None

    def _handle_listar(self, chat_id: int, user_id: str) -> None:
        items = self.vault.items(user_id)
        if not items:
            self.send_message(
                chat_id,
                "Aún no tienes evidencia guardada. Envíame fotos, video, "
                "audio o tu ubicación.",
            )
            return
        lineas = [f"📁 *Tu evidencia* ({len(items)}):\n"]
        for it in items:
            lineas.append(f"{it.seq}. 🕒 {it.when()} — {it.describe()}")
        lineas.append("\nUsa /acta para generar tu reporte o /borrar para eliminarla.")
        self.send_message(chat_id, "\n".join(lineas))

    def _handle_acta(self, chat_id: int, user_id: str) -> None:
        session = self.assistant.sessions.get(user_id)
        acta = self.vault.build_acta(
            user_id, estado=session.estado, vehiculo=session.vehiculo
        )
        self.send_message(chat_id, acta)

    def _handle_analizar(self, chat_id: int, user_id: str) -> None:
        """Analiza con visión la foto más reciente (presunta boleta)."""
        item = self.vault.latest(user_id, KIND_FOTO)
        if item is None:
            self.send_message(
                chat_id,
                "Primero envíame una *foto* de la boleta o multa y luego usa "
                "/analizar.",
            )
            return
        data = self.vault.file_bytes(user_id, item)
        if not data:
            self.send_message(
                chat_id, "No encontré el archivo de la foto. Envíala de nuevo."
            )
            return
        self.send_typing(chat_id)
        estado = self.assistant.sessions.get(user_id).estado
        image_b64 = base64.b64encode(data).decode("ascii")
        try:
            report = self.boleta.analyze(image_b64, estado=estado)
            self.send_message(chat_id, format_report(report, estado))
        except LLMError as exc:
            log.error("Error de visión analizando boleta: %s", exc)
            self.send_message(
                chat_id,
                "⚠️ No pude analizar la boleta en este momento (error del "
                f"proveedor de IA). Intenta más tarde.\n\n_{exc}_",
            )
        except Exception:
            log.exception("Error inesperado analizando boleta")
            self.send_message(
                chat_id,
                "⚠️ Ocurrió un error al analizar la boleta. Intenta con una "
                "foto más nítida.",
            )

    def run(self) -> None:
        """Inicia el bucle de long polling (bloqueante)."""
        me = self.get_me()
        if not me.get("ok"):
            raise RuntimeError(f"Token de Telegram inválido: {me}")
        username = me["result"].get("username", "desconocido")
        log.info("Bot conectado como @%s. Esperando mensajes...", username)
        print(f"✅ Bot en línea como @{username}. Ctrl+C para detener.")

        self._running = True
        while self._running:
            try:
                for update in self._get_updates():
                    self._handle_update(update)
            except KeyboardInterrupt:
                self._running = False
                print("\n👋 Bot detenido.")
            except Exception:  # pragma: no cover
                log.exception("Error en el bucle principal; continuando.")
                time.sleep(3)


def _split_message(text: str, limit: int = _TELEGRAM_MAX) -> list[str]:
    """Divide un texto largo respetando el límite de Telegram."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > limit:
            if current:
                chunks.append(current)
            # Si una sola línea excede el límite, se corta de forma dura.
            while len(line) > limit:
                chunks.append(line[:limit])
                line = line[limit:]
            current = line
        else:
            current += line
    if current:
        chunks.append(current)
    return chunks
