"""Defensor Vial MX — asistente jurídico de tránsito para CDMX y EDOMEX.

Paquete principal. La Fase 1 (MVP) expone:
- ``defensor_vial.rag``  : carga y recuperación documental (RAG).
- ``defensor_vial.llm``  : capa de generación de lenguaje (proveedor conectable).
- ``defensor_vial.assistant`` : orquestación del flujo de atención.
- ``defensor_vial.bot``  : integración con Telegram.
"""

__version__ = "0.4.0"  # Fase 4 — Evidencia + análisis de boleta con visión
