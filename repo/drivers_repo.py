"""DB access for drivers.

Keep driver metadata (code + full name) in a separate table so responses can
show nicer labels than just the numeric driver id.
"""
from typing import Dict, Any, List, Optional
from db import get_conn


def upsert_drivers(session_id: str, rows: List[Dict[str, Any]]) -> int:
    """Insert/update driver rows for a session. Return how many rows were processed."""
    inserted = 0
    with get_conn() as conn:
        for r in rows:
            # OpenF1 provides driver_number, first_name, last_name
            driver_id = r.get("driver_number") or r.get("driver")
            if driver_id is None:
                continue  # skip unexpected rows

            # Build full name and normalize casing
            first = r.get("first_name")
            last = r.get("last_name")

            if first and last:
                name = f"{first.title()} {last.title()}"
            else:
                raw_name = r.get("full_name") or r.get("name")
                name = raw_name.title() if raw_name else None

            # Generate 3-letter code from last name
            code = (
                r.get("abbreviation")
                or r.get("code")
                or (last[:3].upper() if last else None)
            )

            team = r.get("team_name") or r.get("team")

            conn.execute(
                """
                INSERT INTO drivers (session_id, driver, code, name, team)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id, driver) DO UPDATE SET
                    code=excluded.code,
                    name=excluded.name,
                    team=excluded.team
                """,
                (
                    session_id,
                    str(driver_id),
                    code,
                    name,
                    team,
                ),
            )
            inserted += 1
        conn.commit()
    return inserted


def get_driver_map(session_id: str) -> Dict[str, Dict[str, Optional[str]]]:
    """Return a mapping like: {"1": {"code": "VER", "name": "Max Verstappen", "team": "Red Bull Racing"}, ...}"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT driver, code, name, team FROM drivers WHERE session_id = ?",
            (session_id,),
        ).fetchall()

    return {r["driver"]: {"code": r["code"], "name": r["name"], "team": r["team"]} for r in rows}