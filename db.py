"""SQLite helpers.

Keeps DB setup/connection code in one place.
"""
import sqlite3
from pathlib import Path

DB_PATH = str(Path(__file__).with_name("f1replay.db"))

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                time_sec REAL NOT NULL,
                driver TEXT NOT NULL,
                type TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_session_time ON events(session_id, time_sec)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_session_driver_time ON events(session_id, driver, time_sec)"
        )
        conn.commit()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS drivers (
                session_id TEXT NOT NULL,
                driver TEXT NOT NULL,          -- driver number as string
                code TEXT,
                name TEXT,
                PRIMARY KEY (session_id, driver)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_drivers_session ON drivers(session_id)"
        )

