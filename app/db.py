"""
数据访问层模块 (Data Access Layer - SQLite)

【安全检测全局说明】
1. 本模块负责所有与 SQLite 数据库的交互。
2. 所有 SQL 查询必须严格使用参数化查询（Parameterized Queries），严禁使用字符串拼接（f-string/format）构建 SQL，以彻底杜绝 SQL 注入 (SQLi)。
3. 敏感数据（如密码）仅存储其哈希值，严禁在数据库或日志中记录明文凭证。
4. 生产环境建议将 SQLite 替换为 PostgreSQL/MySQL，并配合连接池（如 SQLAlchemy）使用。
"""

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Optional

from .config import DB_PATH

logger = logging.getLogger(__name__)

# ==========================================
# 1. 常量与安全基线 (Constants & Baselines)
# ==========================================

# 【安全检测说明】限制单次查询的最大返回条数，防止恶意用户请求海量数据导致内存耗尽 (DoS 攻击)
MAX_QUERY_LIMIT = 1000
DEFAULT_QUERY_LIMIT = 50


# ==========================================
# 2. 数据库连接与事务管理 (Connection & Transaction Management)
# ==========================================

@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """
    获取数据库连接的上下文管理器。

    【安全检测说明】
    - 自动管理事务的提交与回滚，确保数据一致性。
    - 使用 finally 块确保连接在任何情况下（包括未捕获异常）都会被关闭，防止文件描述符泄漏。
    """
    # 确保数据库所在目录存在
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # 【安全检测说明】SQLite 默认不启用外键约束，必须显式开启以防止产生孤立数据 (Orphaned Records)
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error("Database transaction failed, rolling back: %s", e)
        raise
    finally:
        conn.close()


# ==========================================
# 3. 数据库初始化 (Database Initialization)
# ==========================================

def init_db() -> None:
    """
    初始化数据库表结构。
    通常在应用启动时调用一次。
    """
    with get_db() as conn:
        cur = conn.cursor()

        # 【安全检测说明】密码字段仅存储哈希值 (password_hash)，严禁存储明文
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
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )

        # 为 user_id 添加索引，加速按用户查询检测记录
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_detections_user_id 
            ON detections(user_id)
            """
        )


# ==========================================
# 4. 用户管理操作 (User Management)
# ==========================================

def create_user(username: str, password_hash: str) -> int:
    """
    创建新用户。

    Args:
        username: 用户名。
        password_hash: 经过安全哈希处理后的密码字符串。

    Returns:
        新创建的用户 ID。
    """
    # 【安全检测说明】使用 UTC 时间，避免服务器时区变更导致的时间错乱
    now = datetime.now(timezone.utc).isoformat()

    with get_db() as conn:
        cur = conn.cursor()
        # 【安全核心】严格使用 ? 参数化查询，防御 SQL 注入
        cur.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, password_hash, now),
        )
        return int(cur.lastrowid or 0)


def get_user_by_username(username: str) -> Optional[sqlite3.Row]:
    """根据用户名查询用户"""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username = ?", (username,))
        return cur.fetchone()


def get_user_by_id(user_id: int) -> Optional[sqlite3.Row]:
    """根据用户 ID 查询用户"""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        return cur.fetchone()


# ==========================================
# 5. 检测记录操作 (Detection Records)
# ==========================================

def save_detection(user_id: int, input_text: str, result: dict[str, Any]) -> int:
    """
    保存 AI 文本检测结果。

    Args:
        user_id: 关联的用户 ID。
        input_text: 用户输入的待检测文本。
        result: 模型返回的检测结果字典。

    Returns:
        新创建的检测记录 ID。
    """
    now = datetime.now(timezone.utc).isoformat()
    result_json = json.dumps(result, ensure_ascii=False)

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO detections (user_id, input_text, result_json, created_at) VALUES (?, ?, ?, ?)",
            (user_id, input_text, result_json, now),
        )
        return int(cur.lastrowid or 0)


def list_detections(user_id: int, limit: int = DEFAULT_QUERY_LIMIT) -> list[dict[str, Any]]:
    """
    获取指定用户的检测记录列表。

    【安全检测说明 - DoS 防护】
    必须对 limit 参数进行上限校验，防止攻击者传入 limit=99999999 导致数据库 OOM 或网络带宽耗尽。
    """
    # 防御性校验：限制最大查询条数
    safe_limit = max(1, min(limit, MAX_QUERY_LIMIT))

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, input_text, result_json, created_at
            FROM detections
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, safe_limit),
        )
        rows = cur.fetchall()

    results: list[dict[str, Any]] = []
    for row in rows:
        try:
            parsed_result = json.loads(row["result_json"])
        except json.JSONDecodeError:
            logger.warning("Failed to parse result_json for detection id=%s", row["id"])
            parsed_result = {}

        results.append(
            {
                "id": row["id"],
                "input_text": row["input_text"],
                "result": parsed_result,
                "created_at": row["created_at"],
            }
        )
    return results


def clear_detections(user_id: int) -> int:
    """
    清空指定用户的所有检测记录。

    Returns:
        被删除的记录条数。
    """
    with get_db() as conn:
        cur = conn.cursor()
        # 【安全核心】必须带有 WHERE 条件，严禁执行无条件的 DELETE 导致全表数据丢失
        cur.execute("DELETE FROM detections WHERE user_id = ?", (user_id,))
        return int(cur.rowcount)