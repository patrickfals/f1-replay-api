const yearSelect = document.getElementById("year");
const meetingSelect = document.getElementById("meeting");
const sessionSelect = document.getElementById("session");
const loadBtn = document.getElementById("loadBtn");
const statusEl = document.getElementById("status");

const playerSection = document.getElementById("player");
const playerTitle = document.getElementById("playerTitle");
const playBtn = document.getElementById("playBtn");
const speedSelect = document.getElementById("speed");
const timeLabel = document.getElementById("timeLabel");
const scrubber = document.getElementById("scrubber");
const leaderboardBody = document.getElementById("leaderboardBody");
const leaderboardTable = document.getElementById("leaderboardTable");

let currentSessionId = null;
let currentSessionType = null;
let racePoints = [];
let minTime = 0;
let maxTime = 0;
let simTime = 0;
let playing = false;
let tickHandle = null;
let scrubDebounce = null;
// Goes up by 1 for every leaderboard request. Lets a request check whether a
// newer one has started since, so an old, late reply can't overwrite newer data.
let latestRequestId = 0;

// True while a leaderboard request is waiting on the server.
let isFetchingLeaderboard = false;

function setStatus(msg, isError = false) {
  statusEl.textContent = msg || "";
  statusEl.classList.toggle("error", isError);
}

// Builds the session id the backend stores data under, e.g. "monza_2024_race".
function slugify(...parts) {
  return parts
    .join("_")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function formatTime(seconds) {
  const sign = seconds < 0 ? "-" : "";
  const abs = Math.abs(Math.round(seconds));
  const m = Math.floor(abs / 60);
  const s = abs % 60;
  return `${sign}${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

// fetch() + JSON parsing. Throws with the server's error message if the request failed,
// so callers can just show err.message.
async function fetchJSON(url, options) {
  const res = await fetch(url, options);
  let body = null;
  try {
    body = await res.json();
  } catch (_) {
    // Response had no JSON body (common for some errors), keep body as null.
  }
  if (!res.ok) {
    const detail = (body && body.detail) || res.statusText;
    throw new Error(detail);
  }
  return body;
}

function initYears() {
  const currentYear = new Date().getFullYear();
  // OpenF1 has full session coverage from 2023 onward.
  for (let y = currentYear; y >= 2023; y--) {
    const opt = document.createElement("option");
    opt.value = y;
    opt.textContent = y;
    yearSelect.appendChild(opt);
  }
}

function isUpcoming(dateStart) {
  return Boolean(dateStart) && new Date(dateStart) > new Date();
}

function resetSelect(select, placeholder) {
  select.innerHTML = "";
  const opt = document.createElement("option");
  opt.value = "";
  opt.textContent = placeholder;
  select.appendChild(opt);
  select.disabled = true;
}

async function loadMeetings() {
  const year = yearSelect.value;
  resetSelect(meetingSelect, "Loading…");
  resetSelect(sessionSelect, "Select a Grand Prix first…");
  loadBtn.disabled = true;
  setStatus("");

  try {
    const data = await fetchJSON(`/openf1/meetings?year=${year}`);
    resetSelect(meetingSelect, "Select a Grand Prix…");
    if (!data.meetings.length) {
      setStatus(`No Grand Prix weekends found for ${year}.`, true);
      return;
    }
    for (const m of data.meetings) {
      const upcoming = isUpcoming(m.date_start);

      let label = m.meeting_name;
      if (m.is_cancelled) label += " (Cancelled)";
      if (upcoming) label += " (Upcoming)";

      const opt = document.createElement("option");
      opt.value = m.meeting_key;
      opt.textContent = label;
      opt.dataset.location = m.location;
      opt.disabled = upcoming; // No data to replay until it has happened
      meetingSelect.appendChild(opt);
    }
    meetingSelect.disabled = false;
  } catch (err) {
    setStatus(`Failed to load Grand Prix list: ${err.message}`, true);
  }
}

async function loadSessions() {
  const meetingKey = meetingSelect.value;
  resetSelect(sessionSelect, "Loading…");
  loadBtn.disabled = true;
  setStatus("");

  if (!meetingKey) return;

  try {
    const data = await fetchJSON(`/openf1/sessions?meeting_key=${meetingKey}`);
    resetSelect(sessionSelect, "Select a session…");
    if (!data.sessions.length) {
      setStatus("No sessions found for this Grand Prix.", true);
      return;
    }
    for (const s of data.sessions) {
      const opt = document.createElement("option");
      opt.value = s.session_key;
      opt.textContent = s.is_cancelled ? `${s.session_name} (Cancelled)` : s.session_name;
      opt.dataset.sessionName = s.session_name;
      opt.dataset.sessionType = s.session_type;
      sessionSelect.appendChild(opt);
    }
    sessionSelect.disabled = false;
  } catch (err) {
    setStatus(`Failed to load sessions: ${err.message}`, true);
  }
}

async function loadSession() {
  const year = yearSelect.value;
  const meetingOpt = meetingSelect.selectedOptions[0];
  const sessionOpt = sessionSelect.selectedOptions[0];
  if (!meetingOpt || !sessionOpt || !sessionOpt.value) return;

  stopPlayback();
  playerSection.hidden = true;
  loadBtn.disabled = true;
  setStatus("Loading session data from OpenF1… this can take a few seconds.");

  const sessionId = slugify(meetingOpt.dataset.location, year, sessionOpt.dataset.sessionName);
  const openf1SessionKey = sessionOpt.value;

  try {
    const data = await fetchJSON(
      `/load?session_id=${encodeURIComponent(sessionId)}&openf1_session_key=${openf1SessionKey}`,
      { method: "POST" }
    );

    currentSessionId = data.session_id;
    currentSessionType = sessionOpt.dataset.sessionType;
    racePoints = sessionOpt.dataset.sessionName === "Sprint"
      ? [8, 7, 6, 5, 4, 3, 2, 1]
      : [25, 18, 15, 12, 10, 8, 6, 4, 2, 1];
    leaderboardTable.classList.toggle("is-race", currentSessionType === "Race");
    // The backend only accepts time_sec >= 0; clamp away any pre-start (formation lap) events.
    minTime = Math.max(0, data.time_range[0] ?? 0);
    maxTime = Math.max(minTime, data.time_range[1] ?? 0);
    simTime = minTime;

    scrubber.min = minTime;
    scrubber.max = maxTime;
    scrubber.value = minTime;

    playerTitle.textContent = `${meetingOpt.textContent} (${year}) — ${sessionOpt.textContent}`;
    playerSection.hidden = false;
    setStatus("");

    await renderLeaderboard();
  } catch (err) {
    setStatus(`Failed to load session: ${err.message}`, true);
  } finally {
    loadBtn.disabled = false;
  }
}

async function renderLeaderboard() {
  timeLabel.textContent = formatTime(simTime);
  scrubber.value = simTime;

  // Take the next request number. If another request starts before this one
  // finishes, isStale() becomes true and this one's result gets thrown away.
  latestRequestId += 1;
  const thisRequestId = latestRequestId;
  const isStale = () => thisRequestId !== latestRequestId;
  const requestedTime = simTime;

  isFetchingLeaderboard = true;
  try {
    const data = await fetchJSON(
      `/leaderboard?session_id=${encodeURIComponent(currentSessionId)}&time_sec=${requestedTime}&session_type=${encodeURIComponent(currentSessionType || "")}`
    );

    // Response arrived late, after a newer request was made. Ignore it.
    if (isStale()) return;

    leaderboardBody.innerHTML = "";
    // Top 3 by championship total get gold/silver/bronze; ties go to the driver ahead on track.
    const podium = data.leaderboard
      .filter(r => champTotal(r) !== null)
      .sort((a, b) => champTotal(b) - champTotal(a) || a.position - b.position)
      .slice(0, 3);
    for (const row of data.leaderboard) {
      const delta = formatDelta(row.delta);
      // Outside a Race, P1 shows their fastest lap instead of "Leader".
      const gapText =
        row.position === 1 && currentSessionType !== "Race"
          ? formatLapTime(row.best_lap)
          : formatGap(row.gap_to_leader, row.position);
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td class="pos" style="--team:${teamColor(row.team)}">${row.position ?? "—"}</td>
        <td class="delta-col ${delta.cls}">${delta.text}</td>
        <td class="gap-col">${gapText}</td>
        <td class="code-col"><span>${teamBadgeHTML(row.team)}${row.code ?? "—"}</span></td>
        <td class="driver-col">${row.name ?? row.driver}<span class="team-sub">${row.team ?? ""}</span></td>
        <td>${row.lap ?? 0}</td>
        <td>${row.pits ?? 0}</td>
        <td class="pts-col">${formatPoints(row, podium.indexOf(row))}</td>
      `;
      leaderboardBody.appendChild(tr);
    }
  } catch (err) {
    if (isStale()) return;
    setStatus(`Failed to fetch leaderboard: ${err.message}`, true);
  } finally {
    // Only the newest request clears the flag; a newer one may still be waiting.
    if (!isStale()) isFetchingLeaderboard = false;
  }
}

// delta = places gained (+) or lost (-) since the starting grid.
function formatDelta(delta) {
  if (delta === null || delta === undefined) return { text: "—", cls: "" };
  if (delta === 0) return { text: "+0", cls: "delta-even" };
  return delta > 0
    ? { text: `+${delta}`, cls: "delta-up" }
    : { text: `${delta}`, cls: "delta-down" };
}

// Championship points before the race + points for the current position, e.g. "75+6=81".
function formatPoints(row, rank) {
  if (row.position === null || row.position === undefined) return "—";
  const gain = racePoints[row.position - 1] ?? 0;
  const start = row.points_start;
  if (start === null || start === undefined) return gain ? `<span class="pts-gain">+${gain}</span>` : "—";
  const medal = ["pts-gold", "pts-silver", "pts-bronze"][rank] ?? "";
  // Same four slots on every row so the totals line up; no gain = total only.
  return `<span class="pts-eqn">
    <span class="pts-start">${gain ? start : ""}</span><span class="pts-gain">${gain ? `+${gain}` : ""}</span><span class="pts-eq">${gain ? "=" : ""}</span><span class="pts-total ${gain ? "" : "pts-flat"} ${medal}">${start + gain}</span>
  </span>`;
}

// Team color for the stripe at the start of each row.
function teamColor(team) {
  return TEAM_BADGES.find(t => team && t.match.test(team))?.color ?? "transparent";
}

// Projected championship total, or null if unknown.
function champTotal(row) {
  if (row.position === null || row.position === undefined) return null;
  if (row.points_start === null || row.points_start === undefined) return null;
  return row.points_start + (racePoints[row.position - 1] ?? 0);
}

function formatGap(gap, position) {
  if (position === 1) return "Leader";
  if (typeof gap === "number") return `+${gap.toFixed(3)}s`;
  if (typeof gap === "string") return gap;
  return "—";
}

function formatLapTime(seconds) {
  if (typeof seconds !== "number") return "—";
  const m = Math.floor(seconds / 60);
  const s = seconds - m * 60;
  return `${m}:${s.toFixed(3).padStart(6, "0")}`;
}

function stopPlayback() {
  playing = false;
  playBtn.textContent = "▶ Play";
  if (tickHandle) {
    clearInterval(tickHandle);
    tickHandle = null;
  }
}

function startPlayback() {
  playing = true;
  playBtn.textContent = "⏸ Pause";
  // Every 0.5s of real time, move the race clock forward 0.5s × speed.
  tickHandle = setInterval(async () => {
    // Skip this tick while the last request is still loading, so slow
    // replies don't pile up and make the leaderboard jump around.
    if (isFetchingLeaderboard) return;
    const speed = Number(speedSelect.value);
    simTime += speed * 0.5;
    if (simTime >= maxTime) {
      simTime = maxTime;
      await renderLeaderboard();
      stopPlayback();
      return;
    }
    await renderLeaderboard();
  }, 500);
}

yearSelect.addEventListener("change", loadMeetings);
meetingSelect.addEventListener("change", loadSessions);
sessionSelect.addEventListener("change", () => {
  loadBtn.disabled = !sessionSelect.value;
});
loadBtn.addEventListener("click", loadSession);

playBtn.addEventListener("click", () => {
  if (!currentSessionId) return;
  if (playing) {
    stopPlayback();
  } else {
    startPlayback();
  }
});

scrubber.addEventListener("input", () => {
  stopPlayback();
  simTime = Number(scrubber.value);
  timeLabel.textContent = formatTime(simTime);
  // Wait until dragging pauses for 120ms before asking the server,
  // instead of sending a request for every pixel the slider moves.
  clearTimeout(scrubDebounce);
  scrubDebounce = setTimeout(renderLeaderboard, 120);
});

initYears();
loadMeetings();
