"""Replay engine.

We store "events" in the database (laps, positions, pit stops).
When timestamps are queried,  events replay in order to rebuild state.

State shape:
state[driver] = {"lap": int, "position": int|None, "pits": int}

"""
from typing import Dict, Any, List

def apply_event(state: Dict[str, Dict[str, Any]], event: Dict[str, Any]) -> None:
    """Apply one event to the in-memory state."""
    driver = event["driver"]

    # Create a default state.
    if driver not in state:
        state[driver] = {"lap": 0, "position": None, "pits": 0}

    event_type = event["type"]

    if event_type == "LAP":
        state[driver]["lap"] = int(event["lap"])

    elif event_type == "POSITION":
        state[driver]["position"] = event["position"]

    elif event_type == "PIT":
        # Some pit events include a running pit_count; if not, we increment by 1.
        if "pit_count" in event:
            state[driver]["pits"] = int(event.get("pit_count") or 0)
        else:
            state[driver]["pits"] += 1


def replay(events: List[Dict[str, Any]], target_time_sec: float) -> Dict[str, Dict[str, Any]]:
    """Rebuild state by applying all events up to target_time_sec."""
    events_sorted = sorted(events, key=lambda e: e["time_sec"])
    state: Dict[str, Dict[str, Any]] = {}

    for e in events_sorted:
        if e["time_sec"] > target_time_sec:
            break
        apply_event(state, e)

    return state
