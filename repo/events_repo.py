"""DB access for events.

This file contains the SQL for the `events` table.
Other modules call these functions instead of writing SQL inline.
"""
import json
from typing import Optional, List, Dict, Any
from db import get_conn

def insert_events(session_id: str, events: List[Dict[str, Any]]) -> int:
    """Insert a batch of events for a session. Returns how many rows were inserted."""
    inserted = 0
    with get_conn() as conn:
        for e in events:
            # Store the full event as JSON to keep DB schema simple.
            conn.execute(
                "INSERT INTO events (session_id, time_sec, driver, type, payload) VALUES (?, ?, ?, ?, ?)",
                (session_id, e["time_sec"], e["driver"], e["type"], json.dumps(e)),
            )
            inserted += 1
        conn.commit()
    return inserted

def delete_session(session_id: str) -> None:
    """Delete all events for a given session_id (used by /reset)."""
    with get_conn() as conn:
        conn.execute("DELETE FROM events WHERE session_id = ?", (session_id,))
        conn.commit()

def load_events(session_id: str, until: Optional[float] = None) -> List[Dict[str, Any]]:
    """Load events for a session, optionally only up to a timestamp."""
    with get_conn() as conn:
        if until is None:
            rows = conn.execute(
                "SELECT payload FROM events WHERE session_id = ? ORDER BY time_sec ASC",
                (session_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT payload FROM events WHERE session_id = ? AND time_sec <= ? ORDER BY time_sec ASC",
                (session_id, until),
            ).fetchall()

    return [json.loads(r["payload"]) for r in rows]
