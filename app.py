"""F1 Replay API (FastAPI)

This is a small API for loading race "events" (laps/positions/pits) into SQLite then rebuilding the race state at a specific timestamp.

Folders:
- services/: calls OpenF1 and normalizes data
- repo/: reads/writes SQLite
- replay/: applies events to build a simple in-memory state
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from typing import Optional
from db import init_db, get_conn
from replay.engine import replay, starting_positions
from repo.events_repo import load_events, insert_events, delete_session
from repo.drivers_repo import upsert_drivers, get_driver_map
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="F1 Replay API")
init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).with_name("frontend")
if FRONTEND_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="ui")

@app.get("/", include_in_schema=False)
def root():
    if FRONTEND_DIR.exists():
        return RedirectResponse(url="/ui/")
    return RedirectResponse(url="/docs")

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
    session_type: Optional[str] = Query(None),
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
    starts = starting_positions(evts)

    # OpenF1 has no live position/gap feed for Practice or Qualifying (only Race),
    # so those session types are classified by fastest lap instead, below.
    is_race = session_type in (None, "Race")

    rows = []
    for driver, info in s.items():
        meta = driver_map.get(driver, {})
        rows.append(
            {
                "driver": driver,
                "code": meta.get("code"),
                "name": meta.get("name"),
                "team": meta.get("team"),
                "position": info.get("position"),
                "start_position": starts.get(driver),
                "lap": info.get("lap"),
                "pits": info.get("pits", 0),
                "gap_to_leader": info.get("gap_to_leader"),
                "best_lap": info.get("best_lap"),
            }
        )

    if is_race:
        # When race data does not include position, if only one driver is missing a position and no one is marked as P1 assume said driver is in first place.
        known_positions = {r["position"] for r in rows if r["position"] is not None}
        missing_rows = [r for r in rows if r["position"] is None]

        if len(missing_rows) == 1 and 1 not in known_positions:
            missing_driver = missing_rows[0]["driver"]
            for r in rows:
                if r["driver"] == missing_driver:
                    r["position"] = 1
                    break
    else:
        # Classify by best lap time so far; drivers without a timed lap yet are unranked.
        timed = sorted((r for r in rows if r["best_lap"] is not None), key=lambda r: r["best_lap"])
        fastest = timed[0]["best_lap"] if timed else None
        for r in rows:
            if r["best_lap"] is None:
                r["position"] = None
                r["gap_to_leader"] = None
        for idx, r in enumerate(timed, start=1):
            r["position"] = idx
            r["gap_to_leader"] = r["best_lap"] - fastest

    # Places gained (+) or lost (-) versus the starting grid slot.
    for r in rows:
        if r["position"] is not None and r["start_position"] is not None:
            r["delta"] = r["start_position"] - r["position"]
        else:
            r["delta"] = None

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
        known_positions = {r["position"] for r in rows if r["position"] is not None}
        missing_rows = [r for r in rows if r["position"] is None]
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


def _do_ingest_openf1(
    session_id: str,
    openf1_session_key: int,
    limit_laps: int = 5000,
    limit_positions: int = 5000,
    limit_pits: int = 5000,
):
    """Shared by /ingest/openf1 and /load so the logic isn't duplicated."""
    logger.info(
        f"Ingest started | session={session_id} | openf1_session_key={openf1_session_key}"
    )

    from services.openf1 import (
        fetch_session_start,
        fetch_lap_events,
        fetch_position_events,
        fetch_pit_events,
        fetch_gap_events,
    )

    session_start = fetch_session_start(openf1_session_key)

    # These four calls are independent OpenF1 requests; OpenF1's per-endpoint
    # latency (not our own processing) dominates ingest time, so run them
    # concurrently instead of stacking up their wait times sequentially.
    with ThreadPoolExecutor(max_workers=4) as executor:
        lap_future = executor.submit(fetch_lap_events, openf1_session_key, session_start, limit_laps)
        pos_future = executor.submit(fetch_position_events, openf1_session_key, session_start, limit_positions)
        pit_future = executor.submit(fetch_pit_events, openf1_session_key, session_start, limit_pits)
        gap_future = executor.submit(fetch_gap_events, openf1_session_key, session_start)

        lap_events = lap_future.result()
        pos_events = pos_future.result()
        pit_events = pit_future.result()
        gap_events = gap_future.result()

    inserted = 0
    inserted += insert_events(session_id, lap_events)
    inserted += insert_events(session_id, pos_events)
    inserted += insert_events(session_id, pit_events)
    inserted += insert_events(session_id, gap_events)

    if inserted == 0:
        logger.error(
            f"Ingest failed | session={session_id} | openf1_session_key={openf1_session_key}"
        )
        raise HTTPException(
            status_code=400,
            detail=(
                "No events were ingested. Check session_key, or this session may have "
                "no data because the event was cancelled or didn't go ahead (e.g. weather)."
            ),
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
            "gaps": len(gap_events),
        },
    }


@app.post("/ingest/openf1")
def ingest_openf1(
    session_id: str = Query(...),
    openf1_session_key: int = Query(...),
    limit_laps: int = Query(5000),
    limit_positions: int = Query(5000),
    limit_pits: int = Query(5000),
):
    return _do_ingest_openf1(session_id, openf1_session_key, limit_laps, limit_positions, limit_pits)


def _do_ingest_openf1_drivers(session_id: str, openf1_session_key: int):
    """Shared by /ingest/openf1/drivers and /load so the logic isn't duplicated."""
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


@app.post("/ingest/openf1/drivers")
def ingest_openf1_drivers(
    session_id: str = Query(...),
    openf1_session_key: int = Query(...),
):
    return _do_ingest_openf1_drivers(session_id, openf1_session_key)


# Frontend for year -> Grand Prix -> session picker, no need for session key or swagger 


@app.get("/openf1/meetings")
def openf1_meetings(year: int = Query(...)):
    """List Grand Prix weekends ('meetings') for a season, for the location picker."""
    from services.openf1 import fetch_meetings

    try:
        meetings = fetch_meetings(year)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch meetings from OpenF1: {e}")

    return {"year": year, "meetings": meetings}


@app.get("/openf1/sessions")
def openf1_sessions(meeting_key: int = Query(...)):
    """List sessions for a Grand Prix weekend."""
    from services.openf1 import fetch_sessions_for_meeting

    try:
        sess = fetch_sessions_for_meeting(meeting_key)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch sessions from OpenF1: {e}")

    return {"meeting_key": meeting_key, "sessions": sess}


@app.post("/load")
def load_session(
    session_id: str = Query(...),
    openf1_session_key: int = Query(...),
):
    """One-click load for the frontend: reset, ingest events, and ingest drivers for a session."""
    delete_session(session_id)

    _do_ingest_openf1(session_id, openf1_session_key)

    try:
        _do_ingest_openf1_drivers(session_id, openf1_session_key)
    except HTTPException:
        logger.warning(f"No driver metadata available for session_key={openf1_session_key}")

    with get_conn() as conn:
        row = conn.execute(
            "SELECT MIN(time_sec) as min_t, MAX(time_sec) as max_t FROM events WHERE session_id = ?",
            (session_id,),
        ).fetchone()

        # Sessions open well before the green flag (grid formation, installation laps).
        # Start playback at the first lap-1 event instead of session-open so nothing
        # sits static through the pre-race procedure.
        green_flag = conn.execute(
            """
            SELECT MIN(time_sec) as t FROM events
            WHERE session_id = ? AND type = 'LAP' AND json_extract(payload, '$.lap') = 1
            """,
            (session_id,),
        ).fetchone()

    min_t = row["min_t"]
    if green_flag["t"] is not None:
        min_t = green_flag["t"]

    return {
        "session_id": session_id,
        "openf1_session_key": openf1_session_key,
        "time_range": [min_t, row["max_t"]],
    }
