"""SQLite 连接管理。单连接 + 写锁，保证“重叠检查 + 插入”原子完成。"""
import os
import sqlite3
import threading

SCHEMA = """
CREATE TABLE IF NOT EXISTS artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    annual_budget_lux_hours REAL NOT NULL CHECK (annual_budget_lux_hours > 0),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS exhibitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    artifact_id INTEGER NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
    start_time TEXT NOT NULL,          -- ISO 8601，naive（本地时间或已归一到 UTC）
    end_time TEXT NOT NULL,
    avg_lux REAL NOT NULL CHECK (avg_lux >= 0),
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (end_time > start_time)
);

CREATE INDEX IF NOT EXISTS idx_exhibitions_artifact_time
    ON exhibitions(artifact_id, start_time, end_time);
"""

_conn: sqlite3.Connection | None = None
_lock = threading.RLock()


def init(path: str) -> None:
    """初始化数据库连接并建表。传入 ':memory:' 可用于测试。"""
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
        if path != ":memory:":
            directory = os.path.dirname(os.path.abspath(path))
            os.makedirs(directory, exist_ok=True)
        _conn = sqlite3.connect(path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA foreign_keys = ON")
        _conn.executescript(SCHEMA)


def conn() -> sqlite3.Connection:
    if _conn is None:
        raise RuntimeError("数据库未初始化")
    return _conn


def lock() -> threading.RLock:
    return _lock
