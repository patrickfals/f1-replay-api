"""F1 Replay API (FastAPI)

This is a small API for loading race "events" (laps/positions/pits) into SQLite then rebuilding the race state at a specific timestamp.

Folders:
- services/: calls OpenF1 and normalizes data
- repo/: reads/writes SQLite
- replay/: applies events to build a simple in-memory state
"""
from fastapi import FastAPI, Query, HTTPException
from typing import Optional
from db import init_db
from replay.engine import replay
from repo.events_repo import load_events, insert_events, delete_session
from repo.drivers_repo import upsert_drivers, get_driver_map
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="F1 Replay API")
init_db()


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/reset")
def reset(session_id: str = Query("bahrain_demo")):
    delete_session(session_id)
    return {"ok": True, "session_id": session_id}


@app.get("/events")
def events(
    session_id: str = Query("bahrain_demo"),
    until: Optional[float] = Query(None),
):
    evts = load_events(session_id, until)
    return {"session_id": session_id, "until": until, "events": evts}


@app.get("/state")
def state(
    session_id: str = Query("bahrain_demo"),
    time_sec: float = Query(...),
    driver: Optional[str] = Query(None),
):
    if time_sec < 0:
        raise HTTPException(status_code=400, detail="time_sec must be >= 0")

    evts = load_events(session_id, until=time_sec)

    if not evts:
        raise HTTPException(
            status_code=404,
            detail="Session not found or no events loaded",
        )

    s = replay(evts, time_sec)

    if driver:
        return {
            "session_id": session_id,
            "time_sec": time_sec,
            "driver": driver,
            "state": {driver: s.get(driver, {"lap": 0, "position": None, "pits": 0})},
        }

    return {"session_id": session_id, "time_sec": time_sec, "state": s}


@app.get("/sessions")
def sessions():
    from db import get_conn

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT session_id,
                   COUNT(*) as event_count,
                   MIN(time_sec) as min_t,
                   MAX(time_sec) as max_t
            FROM events
            GROUP BY session_id
            ORDER BY session_id
            """
        ).fetchall()

    return {
        "sessions": [
            {
                "session_id": r["session_id"],
                "event_count": r["event_count"],
                "time_range": [r["min_t"], r["max_t"]],
            }
            for r in rows
        ]
    }


@app.get("/leaderboard")
def leaderboard(
    session_id: str = Query("bahrain_demo"),
    time_sec: float = Query(...),
    debug: bool = Query(False),
):
    if time_sec < 0:
        raise HTTPException(status_code=400, detail="time_sec must be >= 0")

    evts = load_events(session_id, until=time_sec)

    if not evts:
        raise HTTPException(
            status_code=404,
            detail="Session not found or no events loaded",
        )

    s = replay(evts, time_sec)
    driver_map = get_driver_map(session_id)

    rows = []
    for driver, info in s.items():
        meta = driver_map.get(driver, {})
        rows.append(
            {
                "driver": driver,
                "code": meta.get("code"),
                "name": meta.get("name"),
                "position": info.get("position"),
                "lap": info.get("lap"),
                "pits": info.get("pits", 0),
            }
        )

    # Sometimes race data does not include position, if only one driver is missing a position and no one is marked as P1, assume said driver is in first place.
    known_positions = {r["position"] for r in rows if r["position"] is not None}
    missing_rows = [r for r in rows if r["position"] is None]

    if len(missing_rows) == 1 and 1 not in known_positions:
        missing_driver = missing_rows[0]["driver"]
        for r in rows:
            if r["driver"] == missing_driver:
                r["position"] = 1
                break

    rows.sort(
        key=lambda r: (
            r["position"] is None,
            r["position"] if r["position"] is not None else 9999,
        )
    )

    response = {
        "session_id": session_id,
        "time_sec": time_sec,
        "leaderboard": rows,
    }

    if debug:
        known_sorted = sorted([p for p in known_positions if p is not None])
        response["debug"] = {
            "known_positions_count": len(known_sorted),
            "known_positions_sample": known_sorted[:20],
            "missing_position_drivers": [r["driver"] for r in missing_rows],
        }

    return response


@app.post("/seed")
def seed(session_id: str = Query("bahrain_demo")):
    sample_events = [
        {"time_sec": 10, "driver": "VER", "type": "LAP", "lap": 1},
        {"time_sec": 25, "driver": "LEC", "type": "LAP", "lap": 1},
        {"time_sec": 30, "driver": "VER", "type": "PIT", "pit_count": 1},
        {"time_sec": 40, "driver": "VER", "type": "POSITION", "position": 1},
    ]

    inserted = insert_events(session_id, sample_events)

    if inserted == 0:
        raise HTTPException(status_code=400, detail="Seed failed")

    return {"session_id": session_id, "inserted": inserted}


@app.post("/ingest/openf1")
def ingest_openf1(
    session_id: str = Query(...),
    openf1_session_key: int = Query(...),
    limit_laps: int = Query(500),
    limit_positions: int = Query(2000),
    limit_pits: int = Query(2000),
):
    logger.info(
        f"Ingest started | session={session_id} | openf1_session_key={openf1_session_key}"
    )

    from services.openf1 import (
        fetch_session_start,
        fetch_lap_events,
        fetch_position_events,
        fetch_pit_events,
    )

    session_start = fetch_session_start(openf1_session_key)

    lap_events = fetch_lap_events(openf1_session_key, session_start, limit=limit_laps)
    pos_events = fetch_position_events(openf1_session_key, session_start, limit=limit_positions)
    pit_events = fetch_pit_events(openf1_session_key, session_start, limit=limit_pits)

    inserted = 0
    inserted += insert_events(session_id, lap_events)
    inserted += insert_events(session_id, pos_events)
    inserted += insert_events(session_id, pit_events)

    if inserted == 0:
        logger.error(
            f"Ingest failed | session={session_id} | openf1_session_key={openf1_session_key}"
        )
        raise HTTPException(
            status_code=400,
            detail="No events were ingested. Check session_key.",
        )

    logger.info(
        f"Ingest finished | session={session_id} | total_inserted={inserted}"
    )

    return {
        "session_id": session_id,
        "openf1_session_key": openf1_session_key,
        "inserted_total": inserted,
        "inserted": {
            "laps": len(lap_events),
            "positions": len(pos_events),
            "pits": len(pit_events),
        },
    }



@app.post("/ingest/openf1/drivers")
def ingest_openf1_drivers(
    session_id: str = Query(...),
    openf1_session_key: int = Query(...),
):
    from services.openf1 import fetch_drivers

    drivers = fetch_drivers(openf1_session_key)
    upserted = upsert_drivers(session_id, drivers)

    if upserted == 0:
        raise HTTPException(
            status_code=400,
            detail="No drivers were ingested. Check session_key.",
        )

    return {
        "session_id": session_id,
        "openf1_session_key": openf1_session_key,
        "upserted": upserted,
    }
