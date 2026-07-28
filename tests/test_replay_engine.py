from replay.engine import apply_event, replay, starting_positions


def test_apply_event_creates_default_state_for_new_driver():
    state = {}
    apply_event(state, {"driver": "1", "type": "LAP", "lap": 1})

    assert state["1"] == {
        "lap": 1,
        "position": None,
        "pits": 0,
        "gap_to_leader": None,
        "best_lap": None,
    }


def test_lap_event_tracks_best_lap_only_when_faster():
    state = {}
    apply_event(state, {"driver": "1", "type": "LAP", "lap": 1, "lap_time": 90.5})
    apply_event(state, {"driver": "1", "type": "LAP", "lap": 2, "lap_time": 89.0})
    apply_event(state, {"driver": "1", "type": "LAP", "lap": 3, "lap_time": 91.0})

    assert state["1"]["lap"] == 3
    assert state["1"]["best_lap"] == 89.0


def test_lap_event_without_lap_time_does_not_clear_best_lap():
    state = {}
    apply_event(state, {"driver": "1", "type": "LAP", "lap": 1, "lap_time": 90.0})
    apply_event(state, {"driver": "1", "type": "LAP", "lap": 2})

    assert state["1"]["best_lap"] == 90.0


def test_position_event_sets_position():
    state = {}
    apply_event(state, {"driver": "1", "type": "POSITION", "position": 3})

    assert state["1"]["position"] == 3


def test_gap_event_sets_gap_to_leader():
    state = {}
    apply_event(state, {"driver": "1", "type": "GAP", "gap": 1.234})

    assert state["1"]["gap_to_leader"] == 1.234


def test_pit_event_increments_when_no_pit_count_given():
    state = {}
    apply_event(state, {"driver": "1", "type": "PIT"})
    apply_event(state, {"driver": "1", "type": "PIT"})

    assert state["1"]["pits"] == 2


def test_pit_event_uses_running_pit_count_when_given():
    state = {}
    apply_event(state, {"driver": "1", "type": "PIT"})
    apply_event(state, {"driver": "1", "type": "PIT", "pit_count": 5})

    assert state["1"]["pits"] == 5


def test_replay_applies_events_in_time_order_regardless_of_input_order():
    events = [
        {"time_sec": 30, "driver": "1", "type": "LAP", "lap": 2},
        {"time_sec": 10, "driver": "1", "type": "LAP", "lap": 1},
    ]

    state = replay(events, target_time_sec=100)

    assert state["1"]["lap"] == 2


def test_replay_excludes_events_after_target_time():
    events = [
        {"time_sec": 10, "driver": "1", "type": "LAP", "lap": 1},
        {"time_sec": 50, "driver": "1", "type": "LAP", "lap": 2},
    ]

    state = replay(events, target_time_sec=20)

    assert state["1"]["lap"] == 1


def test_replay_includes_event_exactly_at_target_time():
    events = [{"time_sec": 20, "driver": "1", "type": "LAP", "lap": 1}]

    state = replay(events, target_time_sec=20)

    assert state["1"]["lap"] == 1


def test_replay_with_no_events_returns_empty_state():
    assert replay([], target_time_sec=100) == {}


def test_starting_positions_uses_earliest_position_event_per_driver():
    events = [
        {"time_sec": 50, "driver": "1", "type": "POSITION", "position": 1},
        {"time_sec": 10, "driver": "1", "type": "POSITION", "position": 3},
        {"time_sec": 20, "driver": "2", "type": "POSITION", "position": 5},
    ]

    starts = starting_positions(events)

    assert starts == {"1": 3, "2": 5}


def test_starting_positions_ignores_non_position_events_and_null_positions():
    events = [
        {"time_sec": 10, "driver": "1", "type": "LAP", "lap": 1},
        {"time_sec": 10, "driver": "1", "type": "POSITION", "position": None},
    ]

    assert starting_positions(events) == {}
