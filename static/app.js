/* Dashboard front-end */
const $ = (id) => document.getElementById(id);

// ---------- Clock & date ----------
function updateClock() {
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, "0");
    const mm = String(now.getMinutes()).padStart(2, "0");
    const ss = String(now.getSeconds()).padStart(2, "0");
    $("clock").textContent = `${hh}:${mm}:${ss}`;
    const opts = { weekday: "long", year: "numeric", month: "long", day: "numeric" };
    $("date-line").textContent = now.toLocaleDateString("en-GB", opts);
}
setInterval(updateClock, 1000);
updateClock();

// ---------- Helpers ----------
async function getJSON(url) { const r = await fetch(url); return r.json(); }
async function postJSON(url, body, method = "POST") {
    const r = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    return r.json();
}
function escapeHtml(s) {
    return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// ---------- Today's game ----------
async function loadTodaysGame() {
    const data = await getJSON("/api/todays_game");
    $("todays-game").textContent = data.game || "Add games to your library";
    const lib = await getJSON("/api/games");
    $("library-count").textContent = `${lib.games.length} games in your library`;
}
$("reroll-btn").addEventListener("click", async () => {
    const r = await postJSON("/api/todays_game/reroll", {});
    if (r.game) $("todays-game").textContent = r.game;
});

// ---------- Currently playing ----------
async function loadCurrent() {
    const d = await getJSON("/api/currently_playing");
    $("current-game").textContent = d.game || "Nothing yet";
    $("current-doing").textContent = d.doing || "";
}

// ---------- Weather ----------
const WEATHER_CODES = {
    0:["Clear sky","☀️"],1:["Mainly clear","🌤️"],2:["Partly cloudy","⛅"],3:["Overcast","☁️"],
    45:["Foggy","🌫️"],48:["Rime fog","🌫️"],51:["Light drizzle","🌦️"],53:["Drizzle","🌦️"],
    55:["Heavy drizzle","🌧️"],61:["Light rain","🌦️"],63:["Rain","🌧️"],65:["Heavy rain","🌧️"],
    71:["Light snow","🌨️"],73:["Snow","❄️"],75:["Heavy snow","❄️"],77:["Snow grains","❄️"],
    80:["Rain showers","🌦️"],81:["Heavy showers","🌧️"],82:["Violent showers","⛈️"],
    85:["Snow showers","🌨️"],86:["Heavy snow showers","❄️"],95:["Thunderstorm","⛈️"],
    96:["Thunderstorm w/ hail","⛈️"],99:["Heavy thunderstorm","⛈️"]
};
function weatherCodeToText(code) {
    const [text, emoji] = WEATHER_CODES[code] || ["Unknown", "?"];
    return `${emoji} ${text}`;
}

function renderWeather(w) {
    $("weather-temp").textContent = `${Math.round(w.temp)}°C`;
    $("weather-desc").textContent = w.description;
    if (w.location) $("weather-title").textContent = `🌤️ Weather — ${w.location}`;
    const bits = [];
    if (w.high != null && w.low != null) bits.push(`H ${Math.round(w.high)}° / L ${Math.round(w.low)}°`);
    if (w.humidity != null) bits.push(`💧 ${w.humidity}%`);
    if (w.wind != null) bits.push(`🌬️ ${Math.round(w.wind)} km/h`);
    $("weather-extra").textContent = bits.join(" • ");
}

async function loadWeather() {
    try {
          const w = await getJSON("/api/weather");
          if (w.error) throw new Error(w.error);
          renderWeather(w);
    } catch {
          $("weather-desc").textContent = "Could not load weather";
    }
}

// ---------- Quote ----------
async function loadQuote() {
    try {
          const q = await getJSON("/api/quote");
          $("quote-text").textContent = `"${q.quote}"`;
          $("quote-author").textContent = q.author ? `— ${q.author}` : "";
    } catch {
          $("quote-text").textContent = "No quote today.";
    }
}

// ---------- Transport ----------
let transportCache = null;
let transportWalkTo = 0;

function renderTransport() {
    if (!transportCache) return;
    const t = transportCache;
    const list = $("transport-list");
    const nowSec = Date.now() / 1000;
    const conns = t.connections || [];
    const future = conns.filter((c) => (c.departure_ts - nowSec) / 60 >= -1);
    const toShow = (future.length ? future : conns).slice(0, 4);
    list.innerHTML = "";
    if (!toShow.length) {
          list.innerHTML = "<div class='tiny'>No upcoming connections found.</div>";
          return;
    }
    toShow.forEach((c, i) => {
          const minsBus = (c.departure_ts - nowSec) / 60;
          const minsLeave = minsBus - transportWalkTo;
          const div = document.createElement("div");
          div.className = "trip" + (i === 0 ? " next" : "");
          const leaveTxt = minsLeave <= 0
            ? `<span class="leave-now">Leave now!</span>`
                  : `Leave in <strong>${Math.max(0, Math.round(minsLeave))} min</strong>`;
          const line = c.bus_line ? c.bus_line : "Bus";
          div.innerHTML = `
                <div class="line-badge">${line}</div>
                      <div class="times">
                              <strong>${c.departure}</strong>${c.arrival ? " → " + c.arrival : ""}
                                      <div class="tiny">Bus in ${Math.max(0, Math.round(minsBus))} min${c.total_minutes != null ? " · total " + c.total_minutes + " min door-to-door" : ""}</div>
                                            </div>
                                                  <div class="advice">${leaveTxt}</div>
                                                      `;
          list.appendChild(div);
    });
}

async function loadTransport() {
    if (!transportCache) {
          $("transport-list").innerHTML = "<div class='tiny'>Loading bus times…</div>";
    }
    try {
          const t = await getJSON("/api/transport");
          if (t.error && !t.from_stop) {
                  $("transport-route").textContent = "Configure your transport stops →";
                  $("transport-list").innerHTML = "<div class='tiny'>Click the edit button to set your stops.</div>";
                  return;
          }
          if (t.error) throw new Error(t.error);
          $("transport-route").textContent = `${t.from_stop} → ${t.to_stop} · ${t.walk_to_stop_min} min walk to stop, ${t.walk_from_stop_min} min from stop`;
          transportCache = t;
          transportWalkTo = t.walk_to_stop_min || 0;
          renderTransport();
    } catch {
          $("transport-list").innerHTML = "<div class='tiny'>Could not load transport times.</div>";
    }
}
setInterval(renderTransport, 1000);
$("refresh-transport-btn").addEventListener("click", loadTransport);

// ---------- Notes ----------
async function loadNotes() {
    const d = await getJSON("/api/notes");
    renderNotes(d.notes || []);
}
function renderNotes(notes) {
    const ul = $("notes-list");
    ul.innerHTML = "";
    if (!notes.length) { $("notes-empty").style.display = "block"; return; }
    $("notes-empty").style.display = "none";
    notes.forEach((n) => {
          const li = document.createElement("li");
          li.className = `note-item note-${n.color || "yellow"}${n.done ? " done" : ""}`;
          li.dataset.id = n.id;
          li.innerHTML = `
                <span class="note-text">${escapeHtml(n.text)}</span>
                      <button class="note-del" title="Delete">✕</button>
                          `;
          li.addEventListener("click", async (e) => {
                  if (e.target.closest(".note-del")) return;
                  const r = await postJSON(`/api/notes/${n.id}`, { done: !n.done }, "PATCH");
                  if (r.notes) renderNotes(r.notes);
          });
          li.querySelector(".note-del").addEventListener("click", async (e) => {
                  e.stopPropagation();
                  const r = await postJSON(`/api/notes/${n.id}`, {}, "DELETE");
                  if (r.notes) renderNotes(r.notes);
          });
          ul.appendChild(li);
    });
}
$("note-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = $("note-input");
    const text = input.value.trim();
    if (!text) return;
    const r = await postJSON("/api/notes", { text });
    if (r.notes) { renderNotes(r.notes); input.value = ""; input.focus(); }
});

// ---------- Modal ----------
const modal = $("modal");
function openModal(title, bodyHtml, onSave) {
    $("modal-title").textContent = title;
    $("modal-body").innerHTML = bodyHtml;
    modal.classList.remove("hidden");
    $("modal-save").onclick = async () => { await onSave(); closeModal(); };
    $("modal-cancel").onclick = closeModal;
}
function closeModal() { modal.classList.add("hidden"); }

// Edit library
$("edit-games-btn").addEventListener("click", async () => {
    const d = await getJSON("/api/games");
    openModal("Edit game library",
                  `<label>One game per line</label>
                       <textarea id="games-textarea">${escapeHtml((d.games || []).join("\n"))}</textarea>`,
                  async () => {
                          const list = ($("games-textarea").value || "").split("\n");
                          await postJSON("/api/games", { games: list });
                          await loadTodaysGame();
                  }
                );
});

// Edit currently playing
$("edit-current-btn").addEventListener("click", async () => {
    const d = await getJSON("/api/currently_playing");
    openModal("Update currently playing",
                  `<label>Game</label>
                       <input id="current-game-input" value="${escapeHtml(d.game || "")}" />
                            <label>What were you doing?</label>
                                 <textarea id="current-doing-input">${escapeHtml(d.doing || "")}</textarea>`,
                  async () => {
                          await postJSON("/api/currently_playing", {
                                    game: $("current-game-input").value,
                                    doing: $("current-doing-input").value,
                          });
                          await loadCurrent();
                  }
                );
});

// Edit transport config
$("edit-transport-btn").addEventListener("click", async () => {
    const d = await getJSON("/api/transport_config");
    openModal("Edit transport settings",
                  `<label>Get on at</label>
                       <input id="from-input" value="${escapeHtml(d.from_stop || "")}" />
                            <label>Get off at</label>
                                 <input id="to-input" value="${escapeHtml(d.to_stop || "")}" />
                                      <label>Walk to stop (minutes)</label>
                                           <input id="walk-to-input" type="number" min="0" value="${d.walk_to_stop_min || 0}" />
                                                <label>Walk from stop (minutes)</label>
                                                     <input id="walk-from-input" type="number" min="0" value="${d.walk_from_stop_min || 0}" />`,
                  async () => {
                          await postJSON("/api/transport_config", {
                                    from_stop: $("from-input").value,
                                    to_stop: $("to-input").value,
                                    walk_to_stop_min: $("walk-to-input").value,
                                    walk_from_stop_min: $("walk-from-input").value,
                          });
                          transportCache = null;
                          await loadTransport();
                  }
                );
});

// Edit weather location
$("edit-weather-btn").addEventListener("click", async () => {
    const d = await getJSON("/api/weather_config");
    openModal("Change weather location",
                  `<label>Location name</label>
                       <input id="weather-name-input" value="${escapeHtml(d.name || "")}" />
                            <label>Latitude</label>
                                 <input id="weather-lat-input" type="number" step="any" value="${d.lat || ""}" />
                                      <label>Longitude</label>
                                           <input id="weather-lon-input" type="number" step="any" value="${d.lon || ""}" />
                                                <label>Timezone (e.g. Europe/Zurich, America/New_York)</label>
                                                     <input id="weather-tz-input" value="${escapeHtml(d.timezone || "")}" />
                                                          <div class="tiny" style="margin-top:8px;">Tip: search your city on <a href="https://www.latlong.net/" target="_blank" rel="noopener">latlong.net</a> to find coordinates.</div>`,
                  async () => {
                          await postJSON("/api/weather_config", {
                                    name: $("weather-name-input").value,
                                    lat: $("weather-lat-input").value,
                                    lon: $("weather-lon-input").value,
                                    timezone: $("weather-tz-input").value,
                          });
                          await loadWeather();
                  }
                );
});

// ---------- Boot ----------
loadTodaysGame();
loadCurrent();
loadWeather();
loadQuote();
loadTransport();
loadNotes();

// Periodic refreshes
setInterval(loadTransport, 30 * 1000);
setInterval(loadWeather, 10 * 60 * 1000);
setInterval(loadTodaysGame, 60 * 1000);
setInterval(loadCurrent, 5 * 1000);
setInterval(loadNotes, 5 * 1000);
