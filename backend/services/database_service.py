"""
Persistencia local de conversaciones con SQLite.

La base solo almacena historial conversacional y metadatos de respuesta.
No almacena ni modifica el dataset agroecológico ni el modelo ML.
Cada operación abre su propia conexión para evitar compartir conexiones
entre hilos de FastAPI.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import config


class ConversacionNoEncontradaError(LookupError):
    pass


def _ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _db_path() -> Path:
    path = Path(config.SQLITE_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def _connection():
    """Abre una conexión y garantiza commit/rollback y cierre real del archivo.

    Importante en Windows: el context manager nativo de sqlite3 hace
    commit/rollback, pero no cierra la conexión; eso puede dejar el .db
    bloqueado temporalmente.
    """
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Crea las tablas si todavía no existen."""
    with _connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                grid_code_contexto INTEGER NULL,
                metadata_json TEXT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id)
                    REFERENCES conversations(id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_messages_conversation_id
                ON messages(conversation_id, id);
            """
        )


def crear_conversacion() -> int:
    ahora = _ahora_iso()
    with _connection() as conn:
        cur = conn.execute(
            "INSERT INTO conversations (created_at, updated_at) VALUES (?, ?)",
            (ahora, ahora),
        )
        return int(cur.lastrowid)


def existe_conversacion(conversation_id: int) -> bool:
    with _connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM conversations WHERE id = ?",
            (int(conversation_id),),
        ).fetchone()
    return row is not None


def _asegurar_conversacion(conversation_id: int) -> None:
    if not existe_conversacion(conversation_id):
        raise ConversacionNoEncontradaError(
            f"No existe la conversación con id {conversation_id}."
        )


def agregar_mensaje(
    conversation_id: int,
    role: str,
    content: str,
    grid_code_contexto: Optional[int] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> int:
    if role not in {"user", "assistant"}:
        raise ValueError("role debe ser 'user' o 'assistant'.")
    if not content or not content.strip():
        raise ValueError("content no puede estar vacío.")

    _asegurar_conversacion(conversation_id)
    ahora = _ahora_iso()
    metadata_json = (
        json.dumps(metadata, ensure_ascii=False) if metadata is not None else None
    )

    with _connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO messages (
                conversation_id, role, content, grid_code_contexto,
                metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                int(conversation_id),
                role,
                content.strip(),
                int(grid_code_contexto) if grid_code_contexto is not None else None,
                metadata_json,
                ahora,
            ),
        )
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (ahora, int(conversation_id)),
        )
        return int(cur.lastrowid)


def obtener_mensajes(conversation_id: int) -> list[dict[str, Any]]:
    _asegurar_conversacion(conversation_id)
    with _connection() as conn:
        rows = conn.execute(
            """
            SELECT id, conversation_id, role, content, grid_code_contexto,
                   metadata_json, created_at
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id ASC
            """,
            (int(conversation_id),),
        ).fetchall()

    mensajes: list[dict[str, Any]] = []
    for row in rows:
        metadata = None
        if row["metadata_json"]:
            try:
                metadata = json.loads(row["metadata_json"])
            except json.JSONDecodeError:
                metadata = None
        mensajes.append(
            {
                "id": int(row["id"]),
                "conversation_id": int(row["conversation_id"]),
                "role": row["role"],
                "content": row["content"],
                "grid_code_contexto": row["grid_code_contexto"],
                "metadata": metadata,
                "created_at": row["created_at"],
            }
        )
    return mensajes


def historial_para_llm(conversation_id: int) -> list[dict[str, str]]:
    """Devuelve únicamente role/content en el formato esperado por chat_service."""
    return [
        {"role": m["role"], "content": m["content"]}
        for m in obtener_mensajes(conversation_id)
    ]


def listar_conversaciones(limite: int = 50) -> list[dict[str, Any]]:
    limite = max(1, min(int(limite), 200))
    with _connection() as conn:
        rows = conn.execute(
            """
            SELECT
                c.id,
                c.created_at,
                c.updated_at,
                COUNT(m.id) AS total_mensajes,
                COALESCE(
                    (
                        SELECT m2.content
                        FROM messages m2
                        WHERE m2.conversation_id = c.id AND m2.role = 'user'
                        ORDER BY m2.id ASC
                        LIMIT 1
                    ),
                    'Nueva conversación'
                ) AS titulo
            FROM conversations c
            LEFT JOIN messages m ON m.conversation_id = c.id
            GROUP BY c.id, c.created_at, c.updated_at
            ORDER BY c.updated_at DESC, c.id DESC
            LIMIT ?
            """,
            (limite,),
        ).fetchall()

    resultado = []
    for row in rows:
        titulo = str(row["titulo"])
        if len(titulo) > 80:
            titulo = titulo[:77].rstrip() + "..."
        resultado.append(
            {
                "id": int(row["id"]),
                "titulo": titulo,
                "total_mensajes": int(row["total_mensajes"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )
    return resultado


def obtener_conversacion(conversation_id: int) -> dict[str, Any]:
    _asegurar_conversacion(conversation_id)
    with _connection() as conn:
        row = conn.execute(
            "SELECT id, created_at, updated_at FROM conversations WHERE id = ?",
            (int(conversation_id),),
        ).fetchone()

    mensajes = obtener_mensajes(conversation_id)
    titulo = next(
        (m["content"] for m in mensajes if m["role"] == "user"),
        "Nueva conversación",
    )
    if len(titulo) > 80:
        titulo = titulo[:77].rstrip() + "..."

    return {
        "id": int(row["id"]),
        "titulo": titulo,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "mensajes": mensajes,
    }


def eliminar_conversacion(conversation_id: int) -> None:
    _asegurar_conversacion(conversation_id)
    with _connection() as conn:
        conn.execute(
            "DELETE FROM conversations WHERE id = ?",
            (int(conversation_id),),
        )
