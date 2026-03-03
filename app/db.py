import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Optional

from .config import DB_PATH


@contextmanager
def sqlite_connection() -> Iterator[sqlite3.Connection]:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with sqlite_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
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
        conn.commit()


def create_user(username: str, password_hash: str) -> int:
    now = datetime.now().isoformat()
    with sqlite_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users(username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, password_hash, now),
        )
        conn.commit()
        return int(cur.lastrowid)


def get_user_by_username(username: str) -> Optional[sqlite3.Row]:
    with sqlite_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username = ?", (username,))
        return cur.fetchone()


def get_user_by_id(user_id: int) -> Optional[sqlite3.Row]:
    with sqlite_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        return cur.fetchone()


def save_detection(user_id: int, input_text: str, result: dict[str, Any]) -> int:
    now = datetime.now().isoformat()
    with sqlite_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO detections(user_id, input_text, result_json, created_at) VALUES (?, ?, ?, ?)",
            (user_id, input_text, json.dumps(result, ensure_ascii=False), now),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_detections(user_id: int, limit: int = 50) -> list[dict[str, Any]]:
    with sqlite_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, input_text, result_json, created_at
            FROM detections
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit),
        )
        rows = cur.fetchall()

    return [
        {
            "id": row["id"],
            "input_text": row["input_text"],
            "result": json.loads(row["result_json"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def clear_detections(user_id: int) -> int:
    with sqlite_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM detections WHERE user_id = ?", (user_id,))
        count = cur.rowcount
        conn.commit()
        return int(count)
