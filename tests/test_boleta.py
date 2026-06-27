"""Pruebas de Fase 4: análisis de boleta de infracción con visión.

    pytest                          # con pytest
    python tests/test_boleta.py    # sin pytest

No requieren red ni credenciales: el cliente de visión se simula con una
respuesta JSON canned, y el cruce de artículos usa la base documental real.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from defensor_vial.boleta import (
    BoletaAnalyzer,
    _normalize_articulos,
    format_report,
    parse_extraction,
)
from defensor_vial.rag.articles import ArticleIndex
from defensor_vial.rag.loader import ESTADO_CDMX, load_knowledge

KNOWLEDGE_DIR = ROOT / "knowledge"


class _DummyVision:
    """Cliente de visión que devuelve una respuesta fija (simula al modelo)."""

    def __init__(self, payload):
        self.payload = payload if isinstance(payload, str) else json.dumps(payload)
        self.calls = 0

    def analyze_image(self, system_prompt, user_prompt, image_b64, mime="image/jpeg"):
        self.calls += 1
        return self.payload


def _index() -> ArticleIndex:
    return ArticleIndex.from_chunks(load_knowledge(KNOWLEDGE_DIR))


# --- Parsing ---

def test_parse_json_plano():
    data = parse_extraction('{"es_boleta": true, "monto": "500"}')
    assert data["es_boleta"] is True
    assert data["monto"] == "500"


def test_parse_json_con_cercas():
    raw = '```json\n{"es_boleta": true}\n```'
    assert parse_extraction(raw)["es_boleta"] is True


def test_parse_basura_no_revienta():
    data = parse_extraction("esto no es json")
    assert data["es_boleta"] is False
    assert data["_parse_error"] is True


# --- Normalización de artículos ---

def test_normaliza_articulos_varios_formatos():
    assert _normalize_articulos(["Art. 50", "Artículo 51 Bis", "  9999 "]) == [
        "50",
        "51 bis",
        "9999",
    ]
    assert _normalize_articulos("artículo 12") == ["12"]
    assert _normalize_articulos([]) == []
    assert _normalize_articulos(None) == []


# --- Construcción del reporte ---

def test_detecta_campos_faltantes():
    payload = {
        "es_boleta": True,
        "autoridad": "Policía Vial",
        "agente_nombre": None,  # falta
        "agente_numero": None,  # falta
        "fecha": "2026-06-07",
        "hora": "14:30",
        "lugar": "Av. Central",
        "placas": "ABC-123",
        "falta_descripcion": "Vuelta prohibida",
        "fundamento_articulos": ["50"],
        "firma_visible": False,  # falta firma
    }
    analyzer = BoletaAnalyzer(_DummyVision(payload), _index())
    report = analyzer.build_report(payload, ESTADO_CDMX)
    assert "Nombre del agente" in report.faltantes
    assert "Número/identificación del agente" in report.faltantes
    assert "Firma del agente" in report.faltantes
    # Los presentes NO deben aparecer como faltantes.
    assert "Fecha" not in report.faltantes


def test_cruza_articulos_con_base():
    payload = {
        "es_boleta": True,
        "fundamento_articulos": ["50", "9999"],
    }
    analyzer = BoletaAnalyzer(_DummyVision(payload), _index())
    report = analyzer.build_report(payload, ESTADO_CDMX)
    # El 50 existe en CDMX; el 9999 no debe poder verificarse.
    assert "50" in report.articulos_en_base
    assert "9999" in report.articulos_no_verificables


def test_no_boleta_corta_el_flujo():
    payload = {"es_boleta": False}
    analyzer = BoletaAnalyzer(_DummyVision(payload), _index())
    report = analyzer.build_report(payload, None)
    assert report.es_boleta is False
    assert report.faltantes == []


def test_analyze_extremo_a_extremo():
    payload = {
        "es_boleta": True,
        "fundamento_articulos": ["50"],
        "agente_nombre": "Juan Pérez",
        "firma_visible": True,
    }
    vision = _DummyVision(payload)
    analyzer = BoletaAnalyzer(vision, _index())
    report = analyzer.analyze("ZmFrZQ==", estado=ESTADO_CDMX)
    assert vision.calls == 1
    assert report.es_boleta is True
    assert "50" in report.articulos_en_base


# --- Formato del reporte ---

def test_formato_reporte_incluye_secciones():
    payload = {
        "es_boleta": True,
        "agente_nombre": None,
        "fundamento_articulos": ["50", "9999"],
        "firma_visible": False,
    }
    analyzer = BoletaAnalyzer(_DummyVision(payload), _index())
    report = analyzer.build_report(payload, ESTADO_CDMX)
    texto = format_report(report, ESTADO_CDMX)
    assert "Análisis de tu boleta" in texto
    assert "Posibles irregularidades" in texto
    assert "Firma del agente" in texto  # faltante listado
    assert "no pude verificarlos" in texto.lower() or "no verificable" in texto.lower()
    assert "no sustituye la asesoría de un abogado" in texto


def test_formato_parse_error():
    report = BoletaAnalyzer(_DummyVision("basura"), _index()).build_report(
        parse_extraction("basura"), None
    )
    texto = format_report(report)
    assert "no pude leer la boleta" in texto.lower()


def _run_all() -> int:
    funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    fallos = 0
    for fn in funcs:
        try:
            fn()
            print(f"  ✅ {fn.__name__}")
        except AssertionError as exc:
            fallos += 1
            print(f"  ❌ {fn.__name__}: {exc}")
        except Exception as exc:
            fallos += 1
            print(f"  💥 {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(funcs) - fallos}/{len(funcs)} pruebas pasaron.")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
