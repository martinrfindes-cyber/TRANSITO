"""Pruebas de Fase 2: índice de artículos y verificación de referencias.

    pytest            # con pytest
    python tests/test_validation.py   # sin pytest
"""

from __future__ import annotations

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

from defensor_vial.assistant import Assistant
from defensor_vial.config import load_config
from defensor_vial.rag.articles import ArticleIndex
from defensor_vial.rag.loader import ESTADO_CDMX, load_knowledge
from defensor_vial.rag.retriever import BM25Retriever, SearchResult
from defensor_vial.validation import extract_article_refs, validate_answer

KNOWLEDGE_DIR = ROOT / "knowledge"


# --- Extracción de referencias ---

def test_extrae_referencias_simples_y_listas():
    assert extract_article_refs("conforme al artículo 50") == {"50"}
    assert extract_article_refs("los artículos 50, 51 y 52") == {"50", "51", "52"}
    assert "3 bis" in extract_article_refs("ver artículo 3 Bis del reglamento")


def test_extrae_referencias_constitucionales():
    refs = extract_article_refs("los artículos 14 y 16 constitucionales")
    assert refs == {"14", "16"}


def test_sin_referencias():
    assert extract_article_refs("no hay citas legales aquí") == set()


# --- Índice de artículos ---

def test_indice_articulos_cdmx():
    chunks = load_knowledge(KNOWLEDGE_DIR)
    idx = ArticleIndex.from_chunks(chunks)
    assert idx.count(ESTADO_CDMX) > 50
    # El artículo 50 de CDMX (alcohol/narcóticos) debe existir.
    assert idx.exists(ESTADO_CDMX, "50")
    chunk = idx.get(ESTADO_CDMX, "50")
    assert chunk is not None
    assert "Artículo 50" in chunk.heading


# --- Verificación de respuestas ---

def _result_for_article(estado: str, ref: str) -> SearchResult:
    idx = ArticleIndex.from_chunks(load_knowledge(KNOWLEDGE_DIR))
    chunk = idx.get(estado, ref)
    assert chunk is not None
    return SearchResult(chunk=chunk, score=1.0)


def test_valida_articulo_respaldado():
    results = [_result_for_article(ESTADO_CDMX, "50")]
    report = validate_answer("Según el artículo 50 del reglamento...", results)
    assert report.ok
    assert "50" in report.supported


def test_detecta_articulo_inventado():
    results = [_result_for_article(ESTADO_CDMX, "50")]
    report = validate_answer(
        "Con base en el artículo 50 y el artículo 9999...", results
    )
    assert not report.ok
    assert "9999" in report.unsupported
    assert "9999" in report.note()


# --- Inyección de artículo explícito en la recuperación ---

def test_inyecta_articulo_explicito():
    cfg = load_config()
    retriever = BM25Retriever(load_knowledge(KNOWLEDGE_DIR))
    a = Assistant(cfg, retriever=retriever, llm=_DummyLLM())
    results = a.retrieve("qué dice el artículo 50 en CDMX", ESTADO_CDMX)
    refs_al_frente = results[0].chunk.heading
    assert "Artículo 50" in refs_al_frente


# --- Flujo completo: advertencia cuando el modelo inventa ---

class _DummyLLM:
    def __init__(self, text="ok"):
        self.text = text

    def complete(self, messages):
        return self.text


def test_answer_anexa_advertencia_si_inventa():
    cfg = load_config()
    retriever = BM25Retriever(load_knowledge(KNOWLEDGE_DIR))
    fabricado = "## Análisis Legal\nSegún el artículo 9999, está prohibido."
    a = Assistant(cfg, retriever=retriever, llm=_DummyLLM(fabricado))
    reply = a.answer("u", "en CDMX me multaron en mi auto")
    assert reply.validation is not None
    assert not reply.validation.ok
    assert "Verificación de referencias" in reply.text


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
