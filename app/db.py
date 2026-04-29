import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Optional, List, Dict

from .config import DB_PATH


# =========================
# Database Configuration
# =========================

@dataclass(frozen=True)
class DatabaseConfig:
    """数据库配置类"""
    path: Path = Path(DB_PATH)


# =========================
# Connection Manager
# =========================

@contextmanager
def sqlite_connection(config: DatabaseConfig = DatabaseConfig()) -> Iterator[sqlite3.Connection]:
    """
    数据库连接上下文管理器，自动处理事务和资源释放

    Args:
        config: 数据库配置对象

    Yields:
        SQLite数据库连接对象
    """
    # 确保数据库目录存在
    config.path.parent.mkdir(parents=True, exist_ok=True)

    # 建立连接
    conn = sqlite3.connect(config.path)
    conn.row_factory = sqlite3.Row  # 返回字典式行对象

    try:
        yield conn
        conn.commit()  # 无异常则提交事务
    except sqlite3.DatabaseError:
        conn.rollback()  # 发生异常则回滚
        raise
    finally:
        conn.close()  # 确保连接被关闭


# =========================
# Internal Helpers
# =========================

def _execute(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> sqlite3.Cursor:
    """执行SQL语句并返回游标"""
    return conn.execute(sql, params)


def _fetch_one(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> Optional[sqlite3.Row]:
    """查询单条记录，返回None表示未找到"""
    return _execute(conn, sql, params).fetchone()


def _fetch_all(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> list[sqlite3.Row]:
    """查询多条记录，返回空列表表示无结果"""
    return _execute(conn, sql, params).fetchall()


# =========================
# Database Initialization
# =========================

def init_db(config: DatabaseConfig = DatabaseConfig()) -> None:
    """
    初始化数据库表结构

    创建两张表:
    - users: 用户信息表
    - detections: 检测记录表
    """
    with sqlite_connection(config) as conn:
        # 用户表
        conn.execute("""
                     CREATE TABLE IF NOT EXISTS users
                     (
                         id
                         INTEGER
                         PRIMARY
                         KEY
                         AUTOINCREMENT,
                         username
                         TEXT
                         UNIQUE
                         NOT
                         NULL,
                         password_hash
                         TEXT
                         NOT
                         NULL,
                         created_at
                         TEXT
                         NOT
                         NULL
                     )
                     """)

        # 检测记录表，级联删除
        conn.execute("""
                     CREATE TABLE IF NOT EXISTS detections
                     (
                         id
                         INTEGER
                         PRIMARY
                         KEY
                         AUTOINCREMENT,
                         user_id
                         INTEGER
                         NOT
                         NULL,
                         input_text
                         TEXT
                         NOT
                         NULL,
                         result_json
                         TEXT
                         NOT
                         NULL,
                         created_at
                         TEXT
                         NOT
                         NULL,
                         FOREIGN
                         KEY
                     (
                         user_id
                     ) REFERENCES users
                     (
                         id
                     ) ON DELETE CASCADE
                         )
                     """)

        # 创建索引优化查询性能
        conn.execute("CREATE INDEX IF NOT EXISTS idx_detections_user_id ON detections(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_detections_created_at ON detections(created_at)")


# =========================
# User Operations
# =========================

def create_user(username: str, password_hash: str, config: DatabaseConfig = DatabaseConfig()) -> int:
    """
    创建新用户

    Args:
        username: 用户名（唯一）
        password_hash: 加密后的密码
        config: 数据库配置

    Returns:
        新创建的用户ID
    """
    now = datetime.now().isoformat()
    with sqlite_connection(config) as conn:
        cur = _execute(
            conn,
            "INSERT INTO users(username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, password_hash, now),
        )
        return cur.lastrowid


def get_user_by_username(username: str, config: DatabaseConfig = DatabaseConfig()) -> Optional[sqlite3.Row]:
    """
    根据用户名查询用户

    Args:
        username: 用户名
        config: 数据库配置

    Returns:
        用户记录行对象，不存在则返回None
    """
    with sqlite_connection(config) as conn:
        return _fetch_one(conn, "SELECT * FROM users WHERE username = ?", (username,))


def get_user_by_id(user_id: int, config: DatabaseConfig = DatabaseConfig()) -> Optional[sqlite3.Row]:
    """
    根据用户ID查询用户

    Args:
        user_id: 用户ID
        config: 数据库配置

    Returns:
        用户记录行对象，不存在则返回None
    """
    with sqlite_connection(config) as conn:
        return _fetch_one(conn, "SELECT * FROM users WHERE id = ?", (user_id,))


def delete_user(user_id: int, config: DatabaseConfig = DatabaseConfig()) -> bool:
    """
    删除用户及其所有关联记录

    Args:
        user_id: 用户ID
        config: 数据库配置

    Returns:
        是否删除成功
    """
    with sqlite_connection(config) as conn:
        cur = _execute(conn, "DELETE FROM users WHERE id = ?", (user_id,))
        return cur.rowcount > 0


def update_user_password(user_id: int, new_password_hash: str, config: DatabaseConfig = DatabaseConfig()) -> bool:
    """
    更新用户密码

    Args:
        user_id: 用户ID
        new_password_hash: 新密码的哈希值
        config: 数据库配置

    Returns:
        是否更新成功
    """
    with sqlite_connection(config) as conn:
        cur = _execute(
            conn,
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (new_password_hash, user_id),
        )
        return cur.rowcount > 0


# =========================
# Detection Operations
# =========================

def save_detection(user_id: int, input_text: str, result: dict[str, Any],
                   config: DatabaseConfig = DatabaseConfig()) -> int:
    """
    保存检测记录

    Args:
        user_id: 用户ID
        input_text: 原始输入文本
        result: 检测结果字典
        config: 数据库配置

    Returns:
        新创建的检测记录ID
    """
    now = datetime.now().isoformat()
    with sqlite_connection(config) as conn:
        cur = _execute(
            conn,
            "INSERT INTO detections(user_id, input_text, result_json, created_at) VALUES (?, ?, ?, ?)",
            (user_id, input_text, json.dumps(result, ensure_ascii=False), now),
        )
        return cur.lastrowid


def get_detection_by_id(detection_id: int, user_id: int, config: DatabaseConfig = DatabaseConfig()) -> Optional[
    dict[str, Any]]:
    """
    根据ID获取单条检测记录（需验证用户权限）

    Args:
        detection_id: 检测记录ID
        user_id: 用户ID（用于权限验证）
        config: 数据库配置

    Returns:
        检测记录字典，不存在或无权限则返回None
    """
    with sqlite_connection(config) as conn:
        row = _fetch_one(
            conn,
            "SELECT id, input_text, result_json, created_at FROM detections WHERE id = ? AND user_id = ?",
            (detection_id, user_id),
        )
        if row is None:
            return None

        return {
            "id": row["id"],
            "input_text": row["input_text"],
            "result": json.loads(row["result_json"]),
            "created_at": row["created_at"],
        }


def list_detections(
        user_id: int,
        limit: int = 50,
        offset: int = 0,
        config: DatabaseConfig = DatabaseConfig()
) -> List[dict[str, Any]]:
    """
    列出用户的检测记录，支持分页

    Args:
        user_id: 用户ID
        limit: 返回记录数量限制
        offset: 偏移量（用于分页）
        config: 数据库配置

    Returns:
        检测记录列表
    """
    with sqlite_connection(config) as conn:
        rows = _fetch_all(
            conn,
            """
            SELECT id, input_text, result_json, created_at
            FROM detections
            WHERE user_id = ?
            ORDER BY id DESC LIMIT ?
            OFFSET ?
            """,
            (user_id, limit, offset),
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


def count_detections(user_id: int, config: DatabaseConfig = DatabaseConfig()) -> int:
    """
    统计用户的检测记录总数

    Args:
        user_id: 用户ID
        config: 数据库配置

    Returns:
        检测记录总数
    """
    with sqlite_connection(config) as conn:
        row = _fetch_one(
            conn,
            "SELECT COUNT(*) as count FROM detections WHERE user_id = ?",
            (user_id,),
        )
        return row["count"] if row else 0


def clear_detections(user_id: int, config: DatabaseConfig = DatabaseConfig()) -> int:
    """
    清空用户的检测记录

    Args:
        user_id: 用户ID
        config: 数据库配置

    Returns:
        删除的记录条数
    """
    with sqlite_connection(config) as conn:
        cur = _execute(conn, "DELETE FROM detections WHERE user_id = ?", (user_id,))
        return cur.rowcount


def delete_detection_by_id(detection_id: int, user_id: int, config: DatabaseConfig = DatabaseConfig()) -> bool:
    """
    删除单条检测记录（需验证用户权限）

    Args:
        detection_id: 检测记录ID
        user_id: 用户ID（用于权限验证）
        config: 数据库配置

    Returns:
        是否删除成功
    """
    with sqlite_connection(config) as conn:
        cur = _execute(
            conn,
            "DELETE FROM detections WHERE id = ? AND user_id = ?",
            (detection_id, user_id),
        )
        return cur.rowcount > 0