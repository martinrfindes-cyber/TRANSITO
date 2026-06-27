"""Subsistema RAG (Retrieval Augmented Generation) de Defensor Vial MX.

Componentes:
- ``loader``    : lee la base de conocimiento en Markdown y la divide en fragmentos.
- ``retriever`` : índice BM25 en Python puro para recuperar fragmentos relevantes.
"""

from .loader import Chunk, load_knowledge
from .retriever import BM25Retriever, SearchResult

__all__ = ["Chunk", "load_knowledge", "BM25Retriever", "SearchResult"]
