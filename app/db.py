import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .config import DB_PATH


def get_conn() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
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
    conn.close()


def create_user(username: str, password_hash: str) -> int:
    conn = get_conn()
    cur = conn.cursor()
    now = datetime.now().isoformat()
    cur.execute(
        "INSERT INTO users(username, password_hash, created_at) VALUES (?, ?, ?)",
        (username, password_hash, now),
    )
    conn.commit()
    user_id = cur.lastrowid
    conn.close()
    return int(user_id)


def get_user_by_username(username: str) -> Optional[sqlite3.Row]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    return row


def get_user_by_id(user_id: int) -> Optional[sqlite3.Row]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row


def save_detection(user_id: int, input_text: str, result: dict[str, Any]) -> int:
    conn = get_conn()
    cur = conn.cursor()
    now = datetime.now().isoformat()
    cur.execute(
        "INSERT INTO detections(user_id, input_text, result_json, created_at) VALUES (?, ?, ?, ?)",
        (user_id, input_text, json.dumps(result, ensure_ascii=False), now),
    )
    conn.commit()
    item_id = cur.lastrowid
    conn.close()
    return int(item_id)


def list_detections(user_id: int, limit: int = 50) -> list[dict[str, Any]]:
    conn = get_conn()
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
    conn.close()

    results: list[dict[str, Any]] = []
    for row in rows:
        results.append(
            {
                "id": row["id"],
                "input_text": row["input_text"],
                "result": json.loads(row["result_json"]),
                "created_at": row["created_at"],
            }
        )
    return results


def clear_detections(user_id: int) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM detections WHERE user_id = ?", (user_id,))
    deleted_count = cur.rowcount
    conn.commit()
    conn.close()
    return int(deleted_count)
