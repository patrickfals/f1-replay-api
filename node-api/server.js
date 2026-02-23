// Node API (Express)
//
// This small service exists to practice Node.js + NPM and to show that the same data can be queried from a different backend language.
// Reads from the SQLite DB created by the Python FastAPI service.

const express = require("express");
const { getDb, DB_PATH } = require("./db");

const app = express();
const PORT = process.env.PORT || 3000;

app.get("/health", (_req, res) => {
  res.json({ ok: true, service: "node-api", db: DB_PATH });
});

app.get("/sessions", (_req, res) => {
  const db = getDb();

  const rows = db.prepare(`
    SELECT session_id,
           COUNT(*) AS event_count,
           MIN(time_sec) AS min_time_sec,
           MAX(time_sec) AS max_time_sec
    FROM events
    GROUP BY session_id
    ORDER BY session_id
  `).all();

  res.json({
    sessions: rows.map(r => ({
      session_id: r.session_id,
      event_count: r.event_count,
      time_range_sec: [r.min_time_sec, r.max_time_sec]
    }))
  });
});

app.get("/leaderboard", (req, res) => {
  const session_id = req.query.session_id;
  const as_of_time_sec = Number(req.query.time_sec);

  if (!session_id) return res.status(400).json({ error: "session_id is required" });
  if (!Number.isFinite(as_of_time_sec) || as_of_time_sec < 0) {
    return res.status(400).json({ error: "time_sec must be a non-negative number" });
  }

  const db = getDb();

  // Build a list of drivers first, then attach each driver's latest known POSITION event
  const rows = db.prepare(`
    WITH drivers AS (
      SELECT DISTINCT driver
      FROM events
      WHERE session_id = ?
        AND time_sec <= ?
        AND driver IS NOT NULL
    ),
    latest_pos AS (
      SELECT driver, position, observed_time_sec
      FROM (
        SELECT
          e.driver AS driver,
          CAST(json_extract(e.payload, '$.position') AS INTEGER) AS position,
          e.time_sec AS observed_time_sec,
          ROW_NUMBER() OVER (
            PARTITION BY e.driver
            ORDER BY e.time_sec DESC, e.rowid DESC
          ) AS rn
        FROM events e
        WHERE e.session_id = ?
          AND e.type = 'POSITION'
          AND e.time_sec <= ?
          AND e.driver IS NOT NULL
      )
      WHERE rn = 1
    )
    SELECT
      d.driver AS driver,
      lp.position AS position,
      lp.observed_time_sec AS observed_time_sec
    FROM drivers d
    LEFT JOIN latest_pos lp ON lp.driver = d.driver
  `).all(session_id, as_of_time_sec, session_id, as_of_time_sec);

  if (rows.length === 0) {
    return res.status(404).json({ error: "No drivers found for this session/time" });
  }

  let leaderboard = rows.map(r => ({
    driver: r.driver,
    position: (r.position === null || r.position === undefined) ? null : Number(r.position),
    observed_time_sec: (r.observed_time_sec === null || r.observed_time_sec === undefined)
      ? null
      : Number(r.observed_time_sec),
    as_of_time_sec
  }));

  // If nobody is P1 AND one driver is missing position, assume that driver is P1.
  const hasP1 = leaderboard.some(x => x.position === 1);
  const missing = leaderboard.filter(x => x.position === null);

  if (!hasP1 && missing.length === 1) {
    missing[0].position = 1;
    missing[0].inferred = true;
  }

  // Sort by position with nulls (unknown position) at the end.
  leaderboard.sort((a, b) => (a.position ?? 9999) - (b.position ?? 9999));

  res.json({ session_id, as_of_time_sec, leaderboard });
});

app.listen(PORT, () => {
  console.log(`Node API listening on http://localhost:${PORT}`);
});
