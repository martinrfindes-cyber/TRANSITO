"""Punto de entrada de Defensor Vial MX.

Uso:
    python main.py                 Inicia el bot de Telegram (long polling).
    python main.py --cli           Modo interactivo en consola (requiere LLM).
    python main.py --retrieve "…"  Muestra los fragmentos recuperados (sin LLM).
    python main.py --check         Valida configuración y base de conocimiento.
"""

from __future__ import annotations

import argparse
import logging
import sys

from defensor_vial import __version__
from defensor_vial.assistant import Assistant, detect_estado, detect_vehiculo
from defensor_vial.config import load_config
from defensor_vial.llm.base import LLMError
from defensor_vial.rag.loader import load_knowledge
from defensor_vial.rag.retriever import BM25Retriever


def _ensure_utf8_console() -> None:
    """La consola de Windows puede usar cp1252; forzamos UTF-8 para los símbolos."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_check(config) -> int:
    """Valida que la base de conocimiento cargue y reporta el estado."""
    print(f"Defensor Vial MX v{__version__} — verificación\n")
    print(f"Carpeta de conocimiento: {config.knowledge_dir}")
    try:
        chunks = load_knowledge(config.knowledge_dir)
    except Exception as exc:
        print(f"❌ No se pudo cargar la base de conocimiento: {exc}")
        return 1
    print(f"✅ Documentos cargados: {len({c.source for c in chunks})} archivos, "
          f"{len(chunks)} fragmentos.")
    by_estado: dict[str, int] = {}
    for c in chunks:
        by_estado[c.estado] = by_estado.get(c.estado, 0) + 1
    print("   Fragmentos por estado:", dict(sorted(by_estado.items())))

    from defensor_vial.rag.articles import ArticleIndex
    from defensor_vial.rag.loader import ESTADO_CDMX, ESTADO_EDOMEX

    idx = ArticleIndex.from_chunks(chunks)
    print(
        f"   Artículos indexados: CDMX={idx.count(ESTADO_CDMX)}, "
        f"EDOMEX={idx.count(ESTADO_EDOMEX)} (verificación de referencias activa)."
    )

    print("\nConfiguración del LLM:")
    print(f"   Proveedor: {config.llm_provider}  Modelo: {config.openai_model}")
    llm_problems = config.validate_for_llm()
    if llm_problems:
        for p in llm_problems:
            print(f"   ⚠️  {p}")
    else:
        print("   ✅ Credenciales de LLM presentes.")

    print("\nTelegram:")
    if config.telegram_bot_token:
        print("   ✅ TELEGRAM_BOT_TOKEN presente.")
    else:
        print("   ⚠️  Falta TELEGRAM_BOT_TOKEN (necesario para el bot).")

    print("\nBóveda de evidencia (Fase 3):")
    print(f"   Carpeta: {config.evidence_dir}")
    print(f"   Tamaño máximo por archivo: {config.evidence_max_mb} MB")
    return 0


def cmd_retrieve(config, query: str, verbose: bool) -> int:
    """Muestra los fragmentos recuperados para una consulta (sin llamar al LLM)."""
    chunks = load_knowledge(config.knowledge_dir)
    retriever = BM25Retriever(chunks)
    estado = detect_estado(query)
    vehiculo = detect_vehiculo(query)
    print(f"Consulta: {query!r}")
    print(f"Estado detectado: {estado or '—'} | Vehículo: {vehiculo or '—'}\n")
    results = retriever.search(query, top_k=config.top_k, estado=estado)
    results = [r for r in results if r.score >= config.min_score]
    if not results:
        print("(Sin fragmentos por encima del umbral mínimo.)")
        return 0
    for i, r in enumerate(results, 1):
        print(f"[{i}] score={r.score:.3f}  {r.chunk.citation}  (estado: {r.chunk.estado})")
        if verbose:
            preview = r.chunk.text.strip().replace("\n", " ")
            print(f"     {preview[:240]}{'…' if len(preview) > 240 else ''}")
    return 0


def cmd_cli(config) -> int:
    """Conversación interactiva en consola (requiere API key del LLM)."""
    problems = config.validate_for_llm()
    if problems:
        print("No se puede iniciar el modo CLI:")
        for p in problems:
            print(f"  - {p}")
        return 1
    assistant = Assistant(config)
    print(f"Defensor Vial MX v{__version__} — modo consola. "
          "Escribe tu consulta ('salir' para terminar).\n")
    user_id = "cli-local"
    while True:
        try:
            msg = input("Tú> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Hasta luego.")
            return 0
        if not msg:
            continue
        if msg.lower() in {"salir", "exit", "quit"}:
            print("👋 Hasta luego.")
            return 0
        if msg.lower() == "/reset":
            assistant.reset(user_id)
            print("🔄 Conversación reiniciada.\n")
            continue
        try:
            reply = assistant.answer(user_id, msg)
        except LLMError as exc:
            print(f"⚠️  Error del LLM: {exc}\n")
            continue
        print(f"\n{reply.text}\n")


def cmd_bot(config) -> int:
    """Inicia el bot de Telegram."""
    from defensor_vial.bot import TelegramBot

    problems = config.validate_for_bot()
    if problems:
        print("No se puede iniciar el bot:")
        for p in problems:
            print(f"  - {p}")
        return 1
    assistant = Assistant(config)
    bot = TelegramBot(config, assistant)
    bot.run()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="defensor-vial-mx",
        description="Asistente jurídico de tránsito para CDMX y EDOMEX (Telegram).",
    )
    parser.add_argument("--cli", action="store_true", help="Modo consola interactivo.")
    parser.add_argument("--retrieve", metavar="CONSULTA",
                        help="Muestra los fragmentos recuperados (sin LLM).")
    parser.add_argument("--check", action="store_true",
                        help="Valida configuración y base de conocimiento.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Logs detallados.")
    args = parser.parse_args(argv)

    _ensure_utf8_console()
    _setup_logging(args.verbose)
    config = load_config()

    if args.check:
        return cmd_check(config)
    if args.retrieve:
        return cmd_retrieve(config, args.retrieve, args.verbose)
    if args.cli:
        return cmd_cli(config)
    return cmd_bot(config)


if __name__ == "__main__":
    sys.exit(main())
