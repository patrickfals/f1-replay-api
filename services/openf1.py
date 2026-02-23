"""OpenF1 API helpers.

Functions fetch data from https://api.openf1.org and convert it into event dicts stored in SQLite.

Notes:
- OpenF1 provides timestamps as ISO date strings.
- Convert them to UTC and then calculate "seconds since session start"
  (time_sec) so everything runs on a single timeline.
"""
import requests
from datetime import datetime, timezone
from typing import Dict, Any, List
import httpx

OPENF1_BASE = "https://api.openf1.org/v1"

def _parse_iso(dt_str: str) -> datetime:
    """Parse an ISO timestamp string and return a timezone-aware UTC datetime."""
    s = dt_str.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def _secs_since(start: datetime, t: datetime) -> float:
    """Seconds between two datetimes (used to compute time_sec)."""
    return (t - start).total_seconds()

def fetch_session_start(openf1_session_key: int) -> datetime:
    """Fetch the session start time from OpenF1."""
    url = "https://api.openf1.org/v1/sessions"
    with httpx.Client(timeout=30.0) as client:
        r = client.get(url, params={"session_key": openf1_session_key})
        r.raise_for_status()
        data = r.json()
    if not data or not data[0].get("date_start"):
        raise ValueError("Session not found or missing date_start")
    return _parse_iso(data[0]["date_start"])

def fetch_lap_events(openf1_session_key: int, session_start: datetime, limit: int = 500) -> List[Dict[str, Any]]:
    """Fetch laps from OpenF1 and return them as normalized event dicts."""
    url = "https://api.openf1.org/v1/laps"
    with httpx.Client(timeout=30.0) as client:
        r = client.get(url, params={"session_key": openf1_session_key})
        r.raise_for_status()
        data = r.json()

    events: List[Dict[str, Any]] = []
    for item in data[:limit]:
        if not item.get("date_start") or item.get("driver_number") is None:
            continue
        t = _parse_iso(item["date_start"])
        events.append({
            "type": "LAP",
            "driver": str(item["driver_number"]),
            "time_sec": _secs_since(session_start, t),
            "lap": item.get("lap_number"),
        })
    return events

def fetch_position_events(openf1_session_key: int, session_start: datetime, limit: int = 2000) -> List[Dict[str, Any]]:
    """Fetch position updates from OpenF1 and return normalized events."""
    url = "https://api.openf1.org/v1/position"
    with httpx.Client(timeout=30.0) as client:
        r = client.get(url, params={"session_key": openf1_session_key})
        r.raise_for_status()
        data = r.json()

    events: List[Dict[str, Any]] = []
    for item in data[:limit]:
        if not item.get("date") or item.get("driver_number") is None:
            continue
        t = _parse_iso(item["date"])
        events.append({
            "type": "POSITION",
            "driver": str(item["driver_number"]),
            "time_sec": _secs_since(session_start, t),
            "position": item.get("position"),
        })
    return events

def fetch_pit_events(openf1_session_key: int, session_start: datetime, limit: int = 500) -> List[Dict[str, Any]]:
    """Fetch pit stops from OpenF1 and return normalized events."""
    url = "https://api.openf1.org/v1/pit"
    with httpx.Client(timeout=30.0) as client:
        r = client.get(url, params={"session_key": openf1_session_key})
        r.raise_for_status()
        data = r.json()

    events: List[Dict[str, Any]] = []
    for item in data[:limit]:
        if not item.get("date") or item.get("driver_number") is None:
            continue
        t = _parse_iso(item["date"])
        events.append({
            "type": "PIT",
            "driver": str(item["driver_number"]),
            "time_sec": _secs_since(session_start, t),
            "pit_count": item.get("pit_count"),
        })
    return events

def fetch_drivers(openf1_session_key: int):
    """
    Fetch driver metadata for a given OpenF1 session key.
    Returns a list of dicts from the OpenF1 /drivers endpoint.
    """
    url = f"{OPENF1_BASE}/drivers"
    params = {"session_key": openf1_session_key}

    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()