import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Optional

from .config import DB_PATH


@dataclass(frozen=True)
class DatabaseConfig:
    path: Path = Path(DB_PATH)


@contextmanager
def sqlite_connection(config: DatabaseConfig = DatabaseConfig()) -> Iterator[sqlite3.Connection]:
    config.path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except sqlite3.DatabaseError:
        conn.rollback()
        raise
    finally:
        conn.close()


def _execute(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> sqlite3.Cursor:
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur


def _fetch_one(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> Optional[sqlite3.Row]:
    return _execute(conn, sql, params).fetchone()


def _fetch_all(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> list[sqlite3.Row]:
    return _execute(conn, sql, params).fetchall()


def init_db(config: DatabaseConfig = DatabaseConfig()) -> None:
    with sqlite_connection(config) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS detections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                input_text TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )


def create_user(username: str, password_hash: str, config: DatabaseConfig = DatabaseConfig()) -> int:
    now = datetime.now().isoformat()
    with sqlite_connection(config) as conn:
        cur = _execute(
            conn,
            "INSERT INTO users(username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, password_hash, now),
        )
        return int(cur.lastrowid)


def get_user_by_username(username: str, config: DatabaseConfig = DatabaseConfig()) -> Optional[sqlite3.Row]:
    with sqlite_connection(config) as conn:
        return _fetch_one(conn, "SELECT * FROM users WHERE username = ?", (username,))


def get_user_by_id(user_id: int, config: DatabaseConfig = DatabaseConfig()) -> Optional[sqlite3.Row]:
    with sqlite_connection(config) as conn:
        return _fetch_one(conn, "SELECT * FROM users WHERE id = ?", (user_id,))


def save_detection(user_id: int, input_text: str, result: dict[str, Any], config: DatabaseConfig = DatabaseConfig()) -> int:
    now = datetime.now().isoformat()
    with sqlite_connection(config) as conn:
        cur = _execute(
            conn,
            "INSERT INTO detections(user_id, input_text, result_json, created_at) VALUES (?, ?, ?, ?)",
            (user_id, input_text, json.dumps(result, ensure_ascii=False), now),
        )
        return int(cur.lastrowid)


def list_detections(user_id: int, limit: int = 50, config: DatabaseConfig = DatabaseConfig()) -> list[dict[str, Any]]:
    with sqlite_connection(config) as conn:
        rows = _fetch_all(
            conn,
            """
            SELECT id, input_text, result_json, created_at
            FROM detections
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit),
        )

    return [
        {
            "id": row["id"],
            "input_text": row["input_text"],
            "result": json.loads(row["result_json"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def clear_detections(user_id: int, config: DatabaseConfig = DatabaseConfig()) -> int:
    with sqlite_connection(config) as conn:
        cur = _execute(conn, "DELETE FROM detections WHERE user_id = ?", (user_id,))
        return int(cur.rowcount)
