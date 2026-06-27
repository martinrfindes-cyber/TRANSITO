"""Pruebas de Fase 3: bóveda de evidencia ("caja negra").

    pytest                              # con pytest
    python tests/test_evidence.py      # sin pytest

No requieren red ni credenciales: la descarga de Telegram vive en el bot, y
aquí se prueba sólo el almacenamiento y el acta con bytes en memoria.
"""

from __future__ import annotations

import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from defensor_vial.evidence import (
    KIND_FOTO,
    KIND_NOTA,
    KIND_UBICACION,
    EvidenceVault,
)


def _vault() -> tuple[EvidenceVault, Path]:
    tmp = Path(tempfile.mkdtemp(prefix="ev_test_"))
    fija = datetime(2026, 6, 7, 14, 32, 5)
    return EvidenceVault(tmp, clock=lambda: fija), tmp


# --- Altas y persistencia ---

def test_guarda_foto_con_sello_y_archivo():
    vault, base = _vault()
    item = vault.add_file("u1", KIND_FOTO, b"\xff\xd8datos", ".jpg", caption="patrulla")
    assert item.seq == 1
    assert item.kind == KIND_FOTO
    assert item.caption == "patrulla"
    # El archivo binario quedó escrito en disco.
    ruta = base / "u1" / item.filename
    assert ruta.exists()
    assert ruta.read_bytes() == b"\xff\xd8datos"
    assert item.when() == "07/06/2026 14:32 hrs"


def test_secuencia_consecutiva_y_persistencia():
    vault, _ = _vault()
    vault.add_file("u1", KIND_FOTO, b"a", ".jpg")
    vault.add_file("u1", KIND_FOTO, b"b", ".jpg")
    item3 = vault.add_location("u1", 19.601, -99.05)
    assert item3.seq == 3
    # Una instancia nueva lee el índice persistido (no estado en memoria).
    otra = EvidenceVault(vault.base_dir)
    items = otra.items("u1")
    assert [it.seq for it in items] == [1, 2, 3]
    assert items[2].kind == KIND_UBICACION


def test_aislamiento_por_usuario():
    vault, _ = _vault()
    vault.add_file("u1", KIND_FOTO, b"a", ".jpg")
    vault.add_file("u2", KIND_FOTO, b"b", ".jpg")
    assert vault.count("u1") == 1
    assert vault.count("u2") == 1
    # El seq de u2 arranca en 1, independiente de u1.
    assert vault.items("u2")[0].seq == 1


def test_ubicacion_genera_url_de_maps():
    vault, _ = _vault()
    item = vault.add_location("u1", 19.601, -99.05)
    url = item.maps_url()
    assert url is not None
    assert "19.601" in url and "-99.05" in url


def test_borrar_elimina_archivos_e_indice():
    vault, base = _vault()
    vault.add_file("u1", KIND_FOTO, b"a", ".jpg")
    vault.add_note("u1", "el oficial no se identificó")
    n = vault.clear("u1")
    assert n == 2
    assert vault.count("u1") == 0
    assert not (base / "u1" / "index.json").exists()


# --- Seguridad: identificadores con separadores de ruta ---

def test_user_id_no_escapa_de_la_carpeta():
    vault, base = _vault()
    vault.add_file("../../malicioso", KIND_FOTO, b"x", ".jpg")
    # No debe crearse nada fuera de base_dir.
    afuera = base.parent / "malicioso"
    assert not afuera.exists()


# --- Acta ---

def test_acta_vacia_invita_a_documentar():
    vault, _ = _vault()
    acta = vault.build_acta("u1")
    assert "ACTA DE HECHOS" in acta
    assert "Aún no has registrado evidencia" in acta


def test_acta_lista_evidencias_con_contexto():
    vault, _ = _vault()
    vault.add_file("u1", KIND_FOTO, b"a", ".jpg", caption="oficial sin placa")
    vault.add_location("u1", 19.601, -99.05)
    acta = vault.build_acta("u1", estado="EDOMEX", vehiculo="automovil")
    assert "Evidencias registradas:* 2" in acta
    assert "EDOMEX" in acta
    assert "oficial sin placa" in acta
    assert "maps.google.com" in acta
    assert "07/06/2026 14:32 hrs" in acta


def test_nota_se_describe_recortada():
    vault, _ = _vault()
    item = vault.add_note("u1", "x" * 200)
    desc = item.describe()
    assert desc.startswith("Nota:")
    assert "…" in desc
    assert item.kind == KIND_NOTA


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
