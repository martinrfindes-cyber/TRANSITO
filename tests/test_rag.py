"""Pruebas del subsistema RAG y de las heurísticas de detección.

Se pueden ejecutar con pytest:
    pytest

o directamente sin pytest:
    python tests/test_rag.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Permite ejecutar el archivo directamente añadiendo la raíz del repo al path.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# La consola de Windows puede usar cp1252; forzamos UTF-8 para imprimir símbolos.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from defensor_vial.assistant import detect_estado, detect_vehiculo
from defensor_vial.rag.loader import (
    ESTADO_AMBOS,
    ESTADO_CDMX,
    ESTADO_EDOMEX,
    Chunk,
    load_knowledge,
)
from defensor_vial.rag.retriever import BM25Retriever, tokenize

KNOWLEDGE_DIR = ROOT / "knowledge"


# --- Tokenización ---

def test_tokenize_normaliza_acentos_y_stopwords():
    toks = tokenize("El conductor fue multado por POLARIZADO en su automóvil")
    assert "polarizado" in toks
    assert "automovil" in toks  # sin acento
    assert "el" not in toks  # stopword eliminada
    assert "su" not in toks


# --- Carga de la base de conocimiento ---

def test_carga_base_conocimiento():
    chunks = load_knowledge(KNOWLEDGE_DIR)
    assert len(chunks) > 0
    sources = {c.source for c in chunks}
    # Documentos clave esperados.
    for esperado in (
        "Reglamento-CDMX.md",
        "Reglamento-Edomex.md",
        "Derechos-del-conductor.md",
        "Polarizados.md",
    ):
        assert esperado in sources, f"Falta {esperado}"


def test_estados_inferidos_correctamente():
    chunks = load_knowledge(KNOWLEDGE_DIR)
    by_source = {}
    for c in chunks:
        by_source.setdefault(c.source, c.estado)
    assert by_source["Reglamento-CDMX.md"] == ESTADO_CDMX
    assert by_source["Reglamento-Edomex.md"] == ESTADO_EDOMEX
    assert by_source["Derechos-del-conductor.md"] == ESTADO_AMBOS


# --- Recuperación BM25 ---

def test_busqueda_recupera_tema_relevante():
    chunks = load_knowledge(KNOWLEDGE_DIR)
    retriever = BM25Retriever(chunks)
    results = retriever.search("me quieren multar por polarizado", top_k=5)
    assert results, "Debe recuperar al menos un fragmento"
    fuentes = {r.chunk.source for r in results}
    assert "Polarizados.md" in fuentes


def test_filtro_por_estado_excluye_otro_estado():
    chunks = load_knowledge(KNOWLEDGE_DIR)
    retriever = BM25Retriever(chunks)
    results = retriever.search("reglamento de transito", top_k=10, estado=ESTADO_CDMX)
    for r in results:
        assert r.chunk.estado in {ESTADO_CDMX, ESTADO_AMBOS}, (
            f"No debería aparecer estado {r.chunk.estado} al filtrar por CDMX"
        )


def test_scores_normalizados_y_ordenados():
    chunks = load_knowledge(KNOWLEDGE_DIR)
    retriever = BM25Retriever(chunks)
    results = retriever.search("alcoholimetro operativo", top_k=5)
    assert results
    assert abs(results[0].score - 1.0) < 1e-9  # mejor resultado normalizado a 1
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)  # orden descendente


def test_sinonimos_recuperan_articulo_real_de_alcohol():
    # "alcoholímetro" no aparece en la ley (usa "alcohol"); el puente de
    # sinónimos debe permitir recuperar artículos reales del reglamento.
    chunks = load_knowledge(KNOWLEDGE_DIR)
    retriever = BM25Retriever(chunks)
    results = retriever.search(
        "me detuvieron en el alcoholimetro", top_k=10, estado=ESTADO_CDMX
    )
    fuentes = {r.chunk.source for r in results}
    assert "Reglamento-CDMX.md" in fuentes, (
        "El puente de sinónimos debe traer artículos del reglamento de CDMX"
    )


def test_reglamentos_oficiales_cargados():
    chunks = load_knowledge(KNOWLEDGE_DIR)
    cdmx = [c for c in chunks if c.source == "Reglamento-CDMX.md"]
    edomex = [c for c in chunks if c.source == "Reglamento-Edomex.md"]
    # Deben existir muchos artículos (no solo la plantilla).
    assert len(cdmx) > 50, f"CDMX tiene pocos fragmentos: {len(cdmx)}"
    assert len(edomex) > 50, f"EDOMEX tiene pocos fragmentos: {len(edomex)}"
    # Algún fragmento debe corresponder a un artículo concreto.
    assert any("Artículo" in c.heading for c in cdmx)


def test_busqueda_sin_coincidencias_devuelve_vacio():
    retriever = BM25Retriever(
        [Chunk(id="x", source="a.md", title="A", heading_path=["A"], text="hola mundo")]
    )
    assert retriever.search("xyzzqq termino inexistente zzz") == []


# --- Heurísticas de detección ---

def test_detecta_estado():
    assert detect_estado("Esto pasó en CDMX") == ESTADO_CDMX
    assert detect_estado("fue en Ecatepec, Estado de México") == ESTADO_EDOMEX
    assert detect_estado("me multaron ayer") is None  # ambiguo


def test_detecta_vehiculo():
    assert detect_vehiculo("iba en mi moto") == "motocicleta"
    assert detect_vehiculo("conducía mi automóvil") == "automovil"
    assert detect_vehiculo("me detuvieron") is None


def _run_all() -> int:
    """Ejecuta todas las pruebas sin depender de pytest."""
    funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    fallos = 0
    for fn in funcs:
        try:
            fn()
            print(f"  ✅ {fn.__name__}")
        except AssertionError as exc:
            fallos += 1
            print(f"  ❌ {fn.__name__}: {exc}")
        except Exception as exc:  # error inesperado
            fallos += 1
            print(f"  💥 {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(funcs) - fallos}/{len(funcs)} pruebas pasaron.")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
