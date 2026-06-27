"""Análisis de boletas de infracción con IA de visión — Fase 4.

El flujo es:
1. Un modelo de visión EXTRAE los datos de la foto de la boleta como JSON
   (no concluye nada jurídico; solo transcribe lo que ve).
2. Python aplica de forma DETERMINISTA:
   - una lista de verificación de los elementos que una boleta suele requerir
     (si faltan, podría ser motivo para impugnar — se plantea como hipótesis);
   - el cruce de los artículos citados contra la base documental
     (:class:`ArticleIndex`), reutilizando la lógica anti-alucinación: si un
     artículo citado en la boleta no está en la base, se dice "no verificable",
     nunca se inventa su contenido.

Separar la extracción (modelo) del juicio (Python) mantiene la restricción
crítica del proyecto: el sistema nunca afirma leyes/sanciones que no estén
respaldadas.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .llm.base import VisionLLMClient
from .rag.articles import ArticleIndex
from .rag.loader import ESTADO_CDMX, ESTADO_EDOMEX

# Captura "50", "Art. 50", "Artículo 51 Bis", etc. → número + sufijo opcional.
_RE_REF = re.compile(
    r"(\d+)\s*(bis|ter|qu[aá]ter|quintus|sexies|septies)?",
    re.IGNORECASE,
)

# Campos que se intentan extraer de la boleta y su etiqueta legible. El orden
# es el del reporte. Los marcados como obligatorios alimentan la lista de
# verificación de posibles irregularidades.
CAMPOS = [
    ("autoridad", "Autoridad o corporación que emite", True),
    ("agente_nombre", "Nombre del agente", True),
    ("agente_numero", "Número/identificación del agente", True),
    ("fecha", "Fecha", True),
    ("hora", "Hora", True),
    ("lugar", "Lugar de los hechos", True),
    ("placas", "Placas del vehículo", True),
    ("falta_descripcion", "Motivo / falta señalada", True),
    ("fundamento_articulos", "Fundamento legal (artículo)", True),
    ("monto", "Monto de la sanción", False),
    ("firma_visible", "Firma del agente", True),
]

VISION_SYSTEM_PROMPT = """\
Eres un asistente que TRANSCRIBE y EXTRAE datos de una fotografía de una boleta \
o acta de infracción de tránsito mexicana. NO opines ni concluyas nada legal: \
solo reporta lo que se ve en la imagen.

Devuelve EXCLUSIVAMENTE un objeto JSON válido (sin texto adicional, sin ```), \
con exactamente estas claves:
- "es_boleta": true/false (¿la imagen parece una boleta/acta de infracción?)
- "autoridad": string o null
- "agente_nombre": string o null
- "agente_numero": string o null
- "fecha": string o null
- "hora": string o null
- "lugar": string o null
- "placas": string o null
- "falta_descripcion": string o null
- "fundamento_articulos": arreglo de strings con SOLO los números de artículo \
citados (p. ej. ["50","51 bis"]); [] si no hay
- "monto": string o null
- "firma_visible": true/false/null
- "texto_transcrito": string con todo el texto legible de la boleta

Usa null cuando un dato no sea visible o legible. No inventes datos."""

VISION_USER_PROMPT = (
    "Extrae los datos de esta boleta de infracción y responde solo con el JSON "
    "indicado."
)


@dataclass
class BoletaReport:
    """Resultado estructurado del análisis de una boleta."""

    es_boleta: bool
    datos: dict  # campo -> valor extraído (crudo)
    faltantes: list[str] = field(default_factory=list)  # etiquetas obligatorias ausentes
    articulos_citados: list[str] = field(default_factory=list)
    articulos_en_base: list[str] = field(default_factory=list)
    articulos_no_verificables: list[str] = field(default_factory=list)
    transcripcion: str = ""


def _strip_json_fences(text: str) -> str:
    """Quita cercas de código ```json ... ``` si el modelo las incluyó."""
    t = text.strip()
    if t.startswith("```"):
        # Quita la primera línea (``` o ```json) y la última cerca.
        lines = t.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


def parse_extraction(raw: str) -> dict:
    """Convierte la respuesta del modelo de visión en un dict tolerante a fallos."""
    try:
        data = json.loads(_strip_json_fences(raw))
    except (json.JSONDecodeError, TypeError):
        return {"es_boleta": False, "_parse_error": True}
    if not isinstance(data, dict):
        return {"es_boleta": False, "_parse_error": True}
    return data


def _is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == "" or value.strip().lower() in {"null", "n/a", "-"}
    if isinstance(value, (list, tuple)):
        return len(value) == 0
    return False


def _normalize_articulos(value) -> list[str]:
    """Normaliza el campo de artículos a refs limpias ('51 bis', '50')."""
    if _is_empty(value):
        return []
    if isinstance(value, str):
        value = [value]
    out: list[str] = []
    for v in value:
        m = _RE_REF.search(str(v))
        if not m:
            continue
        suf = (m.group(2) or "").lower().replace("á", "a")
        ref = f"{m.group(1)} {suf}".strip() if suf else m.group(1)
        if ref not in out:
            out.append(ref)
    return out


class BoletaAnalyzer:
    """Analiza la foto de una boleta: extrae, verifica y cruza con la base."""

    def __init__(self, vision: VisionLLMClient, articles: ArticleIndex):
        self.vision = vision
        self.articles = articles

    def analyze(
        self,
        image_b64: str,
        estado: str | None = None,
        mime: str = "image/jpeg",
    ) -> BoletaReport:
        raw = self.vision.analyze_image(
            VISION_SYSTEM_PROMPT, VISION_USER_PROMPT, image_b64, mime
        )
        data = parse_extraction(raw)
        return self.build_report(data, estado)

    def build_report(self, data: dict, estado: str | None) -> BoletaReport:
        es_boleta = bool(data.get("es_boleta"))
        report = BoletaReport(
            es_boleta=es_boleta,
            datos=data,
            transcripcion=str(data.get("texto_transcrito") or ""),
        )
        if not es_boleta:
            return report

        # Lista de verificación: elementos obligatorios ausentes.
        for clave, etiqueta, obligatorio in CAMPOS:
            if not obligatorio:
                continue
            valor = data.get(clave)
            if clave == "firma_visible":
                # firma: solo se marca faltante si el modelo afirma que NO hay.
                if valor is False:
                    report.faltantes.append(etiqueta)
                continue
            if _is_empty(valor):
                report.faltantes.append(etiqueta)

        # Cruce de artículos citados contra la base documental.
        citados = _normalize_articulos(data.get("fundamento_articulos"))
        report.articulos_citados = citados
        estados = [estado] if estado else [ESTADO_CDMX, ESTADO_EDOMEX]
        for ref in citados:
            if any(self.articles.exists(est, ref) for est in estados):
                report.articulos_en_base.append(ref)
            else:
                report.articulos_no_verificables.append(ref)
        return report


def format_report(report: BoletaReport, estado: str | None = None) -> str:
    """Formatea el reporte como texto Markdown para Telegram."""
    if report.datos.get("_parse_error"):
        return (
            "⚠️ No pude leer la boleta con claridad. Intenta con una foto más "
            "nítida, de frente y con buena luz."
        )
    if not report.es_boleta:
        return (
            "🤔 Esta imagen no parece una boleta o acta de infracción. Si lo es, "
            "envíala más nítida y completa. La guardé como evidencia de todos modos."
        )

    L: list[str] = ["📄 *Análisis de tu boleta de infracción*\n"]

    # Datos detectados.
    L.append("*Datos detectados:*")
    for clave, etiqueta, _ in CAMPOS:
        if clave == "firma_visible":
            valor = report.datos.get(clave)
            txt = {True: "Sí", False: "No", None: "No determinado"}.get(valor, "—")
            L.append(f"  • {etiqueta}: {txt}")
            continue
        valor = report.datos.get(clave)
        if clave == "fundamento_articulos":
            valor = ", ".join(report.articulos_citados) if report.articulos_citados else None
        if _is_empty(valor):
            L.append(f"  • {etiqueta}: _no visible_")
        else:
            L.append(f"  • {etiqueta}: {valor}")

    # Posibles irregularidades (planteadas como hipótesis, no como hecho).
    L.append("\n*Posibles irregularidades:*")
    if report.faltantes:
        L.append(
            "La boleta *no muestra claramente* estos elementos que un acta de "
            "infracción suele requerir. Su ausencia _podría_ ser motivo para "
            "impugnarla (verifícalo con la autoridad o un abogado):"
        )
        for f in report.faltantes:
            L.append(f"  ⚠️ {f}")
    else:
        L.append("  ✅ Se detectaron los elementos básicos esperados.")

    # Cruce de artículos con la base documental.
    L.append("\n*Fundamento legal citado:*")
    if not report.articulos_citados:
        L.append("  • La boleta no muestra un artículo de fundamento legible.")
    else:
        if report.articulos_en_base:
            arts = ", ".join(report.articulos_en_base)
            L.append(
                f"  • Artículo(s) {arts}: están en mi base documental. "
                "Pregúntame “¿qué dice el artículo N?” para revisar si lo "
                "aplicaron correctamente."
            )
        if report.articulos_no_verificables:
            arts = ", ".join(report.articulos_no_verificables)
            L.append(
                f"  • Artículo(s) {arts}: *no pude verificarlos* en mi base "
                "documental de CDMX/EDOMEX. No significa que no existan, pero "
                "conviene confirmarlos."
            )

    L.append(
        "\n⚠️ Análisis informativo automático sobre lo visible en la foto; "
        "no sustituye la asesoría de un abogado. La imagen quedó guardada como "
        "evidencia."
    )
    return "\n".join(L)
