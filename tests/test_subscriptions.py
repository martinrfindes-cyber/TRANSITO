"""Pruebas del padrón de suscriptores (control de acceso de paga).

Sin red ni credenciales: usan un reloj inyectado para fechas deterministas y un
archivo temporal para verificar la persistencia.
"""

from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from defensor_vial.subscriptions import SubscriptionStore  # noqa: E402


class _Clock:
    """Reloj controlable para las pruebas."""

    def __init__(self, now: datetime):
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def _store(tmp: Path, clock: _Clock) -> SubscriptionStore:
    return SubscriptionStore(tmp / "_subscriptions.json", clock=clock)


def test_nuevo_usuario_no_esta_activo():
    with tempfile.TemporaryDirectory() as d:
        store = _store(Path(d), _Clock(datetime(2026, 6, 28, 12, 0)))
        assert store.is_active("123") is False
        assert store.get("123") is None


def test_activar_da_acceso_y_calcula_vencimiento():
    with tempfile.TemporaryDirectory() as d:
        clock = _Clock(datetime(2026, 6, 28, 12, 0))
        store = _store(Path(d), clock)
        sub = store.activate("123", days=30, name="Juan")
        assert store.is_active("123") is True
        assert sub.name == "Juan"
        assert sub.expires_at == "2026-07-28"  # 28 jun + 30 días


def test_acceso_expira_pasada_la_fecha():
    with tempfile.TemporaryDirectory() as d:
        clock = _Clock(datetime(2026, 6, 28, 12, 0))
        store = _store(Path(d), clock)
        store.activate("123", days=10)
        assert store.is_active("123") is True
        # El día del vencimiento sigue vigente...
        clock.now = datetime(2026, 7, 8, 23, 0)
        assert store.is_active("123") is True
        # ...al día siguiente ya no.
        clock.now = datetime(2026, 7, 9, 0, 1)
        assert store.is_active("123") is False


def test_renovar_estando_activo_suma_dias():
    with tempfile.TemporaryDirectory() as d:
        clock = _Clock(datetime(2026, 6, 28, 12, 0))
        store = _store(Path(d), clock)
        store.activate("123", days=30)  # vence 2026-07-28
        sub = store.activate("123", days=30)  # suma, no reinicia
        assert sub.expires_at == "2026-08-27"  # 28 jul + 30 días


def test_renovar_estando_vencido_cuenta_desde_hoy():
    with tempfile.TemporaryDirectory() as d:
        clock = _Clock(datetime(2026, 6, 28, 12, 0))
        store = _store(Path(d), clock)
        store.activate("123", days=10)  # vence 2026-07-08
        clock.now = datetime(2026, 8, 1, 12, 0)  # ya vencido
        sub = store.activate("123", days=30)
        assert sub.expires_at == "2026-08-31"  # 1 ago + 30 días


def test_activar_conserva_fecha_de_primera_alta():
    with tempfile.TemporaryDirectory() as d:
        clock = _Clock(datetime(2026, 6, 28, 12, 0))
        store = _store(Path(d), clock)
        primero = store.activate("123", days=30)
        clock.now = datetime(2026, 7, 1, 12, 0)
        segundo = store.activate("123", days=30)
        assert segundo.activated_at == primero.activated_at


def test_baja_elimina_del_padron():
    with tempfile.TemporaryDirectory() as d:
        store = _store(Path(d), _Clock(datetime(2026, 6, 28, 12, 0)))
        store.activate("123", days=30)
        assert store.deactivate("123") is True
        assert store.is_active("123") is False
        assert store.deactivate("123") is False  # ya no existía


def test_persistencia_entre_instancias():
    with tempfile.TemporaryDirectory() as d:
        clock = _Clock(datetime(2026, 6, 28, 12, 0))
        store = _store(Path(d), clock)
        store.activate("123", days=30, name="Ana")
        # Nueva instancia lee del disco lo guardado.
        store2 = _store(Path(d), clock)
        assert store2.is_active("123") is True
        assert store2.get("123").name == "Ana"


def test_carga_tolera_json_corrupto():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "_subscriptions.json"
        path.write_text("{ esto no es json válido", encoding="utf-8")
        store = SubscriptionStore(path, clock=_Clock(datetime(2026, 6, 28)))
        assert store.all() == []  # no truena, arranca vacío


def test_all_ordena_por_vencimiento():
    with tempfile.TemporaryDirectory() as d:
        clock = _Clock(datetime(2026, 6, 28, 12, 0))
        store = _store(Path(d), clock)
        store.activate("aaa", days=60)
        store.activate("bbb", days=10)
        store.activate("ccc", days=30)
        orden = [s.user_id for s in store.all()]
        assert orden == ["bbb", "ccc", "aaa"]


if __name__ == "__main__":
    import traceback

    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    fallos = 0
    for fn in fns:
        try:
            fn()
            print(f"  ✓ {fn.__name__}")
        except Exception:
            fallos += 1
            print(f"  ✗ {fn.__name__}")
            traceback.print_exc()
    total = len(fns)
    print(f"\n{total - fallos}/{total} pruebas de suscripciones pasaron.")
    sys.exit(1 if fallos else 0)
