"""Smoke test de SQLite. No llama a Gemini ni consume cuota."""

import os
import sys
import tempfile
from pathlib import Path

# Debe definirse antes de importar config/database_service.
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

tmp_dir = tempfile.TemporaryDirectory()
os.environ["SQLITE_DB_PATH"] = str(Path(tmp_dir.name) / "test_chat_history.db")

from services import database_service as db  # noqa: E402


def main():
    db.init_db()
    cid = db.crear_conversacion()
    assert cid > 0

    db.agregar_mensaje(cid, "user", "Hola", grid_code_contexto=4843916)
    db.agregar_mensaje(
        cid,
        "assistant",
        "Hola, ¿en qué te ayudo?",
        metadata={"grid_codes_relacionados": [4843916], "tools_utilizadas": []},
    )

    historial = db.historial_para_llm(cid)
    assert historial == [
        {"role": "user", "content": "Hola"},
        {"role": "assistant", "content": "Hola, ¿en qué te ayudo?"},
    ]

    detalle = db.obtener_conversacion(cid)
    assert len(detalle["mensajes"]) == 2
    assert detalle["mensajes"][1]["metadata"]["grid_codes_relacionados"] == [4843916]

    lista = db.listar_conversaciones()
    assert lista and lista[0]["id"] == cid

    db.eliminar_conversacion(cid)
    assert db.listar_conversaciones() == []

    print("OK: persistencia SQLite de conversaciones y mensajes.")


if __name__ == "__main__":
    main()
