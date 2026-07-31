import pytest
from fastapi.testclient import TestClient

from app import app
from repo.events_repo import delete_session

client = TestClient(app)
TEST_SESSION = "pytest_test_session"


@pytest.fixture(autouse=True)
def isolated_session():
    # Isolates the test runs ensuring database and test runs remain clean.
    delete_session(TEST_SESSION)
    yield
    delete_session(TEST_SESSION)


def seed():
    return client.post("/seed", params={"session_id": TEST_SESSION})


def test_health():
    resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_seed_inserts_sample_events():
    resp = seed()

    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == TEST_SESSION
    assert body["inserted"] == 4


def test_state_rebuilds_from_seeded_events():
    seed()

    resp = client.get("/state", params={"session_id": TEST_SESSION, "time_sec": 100})

    assert resp.status_code == 200
    state = resp.json()["state"]
    assert state["VER"]["lap"] == 1
    assert state["VER"]["pits"] == 1
    assert state["VER"]["position"] == 1


def test_state_for_unknown_session_returns_404():
    resp = client.get(
        "/state", params={"session_id": "no_such_session_at_all", "time_sec": 100}
    )

    assert resp.status_code == 404


def test_state_rejects_negative_time_sec():
    resp = client.get("/state", params={"session_id": TEST_SESSION, "time_sec": -1})

    assert resp.status_code == 400


def test_leaderboard_reflects_seeded_state():
    seed()

    resp = client.get("/leaderboard", params={"session_id": TEST_SESSION, "time_sec": 100})

    assert resp.status_code == 200
    rows = resp.json()["leaderboard"]
    ver_row = next(r for r in rows if r["driver"] == "VER")
    assert ver_row["position"] == 1
    assert ver_row["pits"] == 1


def test_leaderboard_for_unknown_session_returns_404():
    resp = client.get(
        "/leaderboard", params={"session_id": "no_such_session_at_all", "time_sec": 100}
    )

    assert resp.status_code == 404


def test_reset_clears_stored_events():
    seed()

    reset_resp = client.post("/reset", params={"session_id": TEST_SESSION})
    events_resp = client.get("/events", params={"session_id": TEST_SESSION})

    assert reset_resp.status_code == 200
    assert events_resp.json()["events"] == []


def test_sessions_lists_seeded_session():
    seed()

    resp = client.get("/sessions")

    ids = [s["session_id"] for s in resp.json()["sessions"]]
    assert TEST_SESSION in ids
