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

let currentSessionId = null;
let minTime = 0;
let maxTime = 0;
let simTime = 0;
let playing = false;
let tickHandle = null;
let scrubDebounce = null;

function setStatus(msg, isError = false) {
  statusEl.textContent = msg || "";
  statusEl.classList.toggle("error", isError);
}

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

async function fetchJSON(url, options) {
  const res = await fetch(url, options);
  let body = null;
  try {
    body = await res.json();
  } catch (_) {
    // no body
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
      const opt = document.createElement("option");
      opt.value = m.meeting_key;
      opt.textContent = m.meeting_name;
      opt.dataset.location = m.location;
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
      opt.textContent = s.session_name;
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

  const sessionId = slugify(meetingOpt.dataset.location, year, sessionOpt.textContent);
  const openf1SessionKey = sessionOpt.value;

  try {
    const data = await fetchJSON(
      `/load?session_id=${encodeURIComponent(sessionId)}&openf1_session_key=${openf1SessionKey}`,
      { method: "POST" }
    );

    currentSessionId = data.session_id;
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

  try {
    const data = await fetchJSON(
      `/leaderboard?session_id=${encodeURIComponent(currentSessionId)}&time_sec=${simTime}`
    );
    leaderboardBody.innerHTML = "";
    for (const row of data.leaderboard) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td class="pos">${row.position ?? "—"}</td>
        <td>${row.code ?? "—"}</td>
        <td>${row.name ?? row.driver}</td>
        <td>${row.team ?? "—"}</td>
        <td>${row.lap ?? 0}</td>
        <td>${row.pits ?? 0}</td>
      `;
      leaderboardBody.appendChild(tr);
    }
  } catch (err) {
    setStatus(`Failed to fetch leaderboard: ${err.message}`, true);
  }
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
  tickHandle = setInterval(async () => {
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
  clearTimeout(scrubDebounce);
  scrubDebounce = setTimeout(renderLeaderboard, 120);
});

initYears();
loadMeetings();
