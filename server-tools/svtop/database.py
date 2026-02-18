"""SQLite database layer for server metrics storage."""

import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Optional


class Database:
    def __init__(self, db_path: str = "monitor.db"):
        self.db_path = db_path
        self._local = threading.local()

    @property
    def conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
        return self._local.conn

    def init_db(self):
        cur = self.conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                server_name TEXT NOT NULL,
                cpu_percent REAL,
                ram_used_mb REAL,
                ram_total_mb REAL,
                gpu_util REAL,
                gpu_mem_used_mb REAL,
                gpu_mem_total_mb REAL,
                disk_usage_percent REAL
            );

            CREATE TABLE IF NOT EXISTS processes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_id INTEGER NOT NULL,
                pid INTEGER,
                user TEXT,
                cpu_percent REAL,
                mem_percent REAL,
                command TEXT,
                FOREIGN KEY (metric_id) REFERENCES metrics(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS logged_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_id INTEGER NOT NULL,
                username TEXT,
                terminal TEXT,
                login_time TEXT,
                FOREIGN KEY (metric_id) REFERENCES metrics(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_metrics_server_ts
                ON metrics(server_name, timestamp);
            CREATE INDEX IF NOT EXISTS idx_processes_metric
                ON processes(metric_id);
            CREATE INDEX IF NOT EXISTS idx_users_metric
                ON logged_users(metric_id);
        """)
        self.conn.commit()

    def insert_metric(self, server_name: str, cpu: float, ram_used: float,
                      ram_total: float, gpu_util: Optional[float],
                      gpu_mem_used: Optional[float], gpu_mem_total: Optional[float],
                      disk_percent: float) -> int:
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO metrics (timestamp, server_name, cpu_percent,
                ram_used_mb, ram_total_mb, gpu_util, gpu_mem_used_mb,
                gpu_mem_total_mb, disk_usage_percent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.utcnow().isoformat(),
            server_name, cpu, ram_used, ram_total,
            gpu_util, gpu_mem_used, gpu_mem_total, disk_percent
        ))
        self.conn.commit()
        return cur.lastrowid

    def insert_processes(self, metric_id: int, processes: list[dict]):
        cur = self.conn.cursor()
        cur.executemany("""
            INSERT INTO processes (metric_id, pid, user, cpu_percent, mem_percent, command)
            VALUES (?, ?, ?, ?, ?, ?)
        """, [
            (metric_id, p.get("pid"), p.get("user"), p.get("cpu"), p.get("mem"), p.get("command"))
            for p in processes
        ])
        self.conn.commit()

    def insert_users(self, metric_id: int, users: list[dict]):
        cur = self.conn.cursor()
        cur.executemany("""
            INSERT INTO logged_users (metric_id, username, terminal, login_time)
            VALUES (?, ?, ?, ?)
        """, [
            (metric_id, u.get("username"), u.get("terminal"), u.get("login_time"))
            for u in users
        ])
        self.conn.commit()

    def get_servers(self) -> list[str]:
        cur = self.conn.cursor()
        cur.execute("SELECT DISTINCT server_name FROM metrics ORDER BY server_name")
        return [row["server_name"] for row in cur.fetchall()]

    def get_metrics(self, server_name: str, hours: int = 24) -> list[dict]:
        since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        cur = self.conn.cursor()
        cur.execute("""
            SELECT * FROM metrics
            WHERE server_name = ? AND timestamp >= ?
            ORDER BY timestamp ASC
        """, (server_name, since))
        return [dict(row) for row in cur.fetchall()]

    def get_latest_metric(self, server_name: str) -> Optional[dict]:
        cur = self.conn.cursor()
        cur.execute("""
            SELECT * FROM metrics
            WHERE server_name = ?
            ORDER BY timestamp DESC LIMIT 1
        """, (server_name,))
        row = cur.fetchone()
        return dict(row) if row else None

    def get_processes(self, metric_id: int) -> list[dict]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM processes WHERE metric_id = ? ORDER BY cpu_percent DESC", (metric_id,))
        return [dict(row) for row in cur.fetchall()]

    def get_users(self, metric_id: int) -> list[dict]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM logged_users WHERE metric_id = ?", (metric_id,))
        return [dict(row) for row in cur.fetchall()]

    def cleanup_old_data(self, retention_days: int = 30):
        cutoff = (datetime.utcnow() - timedelta(days=retention_days)).isoformat()
        cur = self.conn.cursor()
        cur.execute("DELETE FROM metrics WHERE timestamp < ?", (cutoff,))
        self.conn.commit()
