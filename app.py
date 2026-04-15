"""
General Personal Dashboard
Local:  python3 app.py   ->   http://localhost:5050
Cloud:  Render runs `gunicorn app:app` using DATABASE_URL env var.
"""
import json, os, random, re, uuid
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, jsonify, request
from sqlalchemy import create_engine, Column, String, Text
from sqlalchemy.orm import sessionmaker, declarative_base
import requests

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DEFAULT_LAT, DEFAULT_LON = 40.7128, -74.0060
DEFAULT_LOCATION_NAME = "New York"
DEFAULT_TIMEZONE = "America/New_York"
NOTE_COLORS = ["yellow", "pink", "blue", "green", "purple", "orange"]

DEFAULT_GAMES = [
    "The Legend of Zelda: Breath of the Wild", "Minecraft", "Elden Ring",
    "Stardew Valley", "Hollow Knight", "Hades",
]
DEFAULT_CURRENT = {"game": "", "doing": ""}
DEFAULT_TRANSPORT = {"from_stop": "", "to_stop": "",
                     "walk_to_stop_min": 5, "walk_from_stop_min": 3}
DEFAULT_WEATHER_CONFIG = {
    "lat": DEFAULT_LAT, "lon": DEFAULT_LON,
    "name": DEFAULT_LOCATION_NAME, "timezone": DEFAULT_TIMEZONE
}

DB_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DATA_DIR}/dashboard.db")
if DB_URL.startswith("postgres://"):
    DB_URL = DB_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DB_URL, pool_pre_ping=True)
Session = sessionmaker(bind=engine)
Base = declarative_base()

class KV(Base):
    __tablename__ = "kv"
    key = Column(String(64), primary_key=True)
    value = Column(Text)

Base.metadata.create_all(engine)

def kv_load(key, default):
    with Session() as s:
        row = s.get(KV, key)
        if row is None:
            kv_save(key, default)
            return default
        try:
            return json.loads(row.value)
        except Exception:
            return default

def kv_save(key, data):
    with Session() as s:
        row = s.get(KV, key)
        payload = json.dumps(data, ensure_ascii=False)
        if row is None:
            s.add(KV(key=key, value=payload))
        else:
            row.value = payload
        s.commit()

def migrate_legacy_files():
    mapping = [("games", DATA_DIR / "games.json"),
               ("currently_playing", DATA_DIR / "currently_playing.json"),
               ("transport", DATA_DIR / "transport.json"),
               ("today_pick", DATA_DIR / "today_pick.json"),
               ("notes", DATA_DIR / "notes.json")]
    for key, path in mapping:
        if not path.exists():
            continue
        with Session() as s:
            if s.get(KV, key) is not None:
                continue
        try:
            kv_save(key, json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            pass

migrate_legacy_files()

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/healthz")
def healthz():
    return jsonify({"ok": True, "t": datetime.utcnow().isoformat()})

@app.route("/api/todays_game")
def todays_game():
    games = kv_load("games", DEFAULT_GAMES)
    if not games:
        return jsonify({"game": None})
    today = datetime.now().strftime("%Y-%m-%d")
    pick = kv_load("today_pick", {})
    if pick.get("date") != today or pick.get("game") not in games:
        pick = {"date": today, "game": random.choice(games)}
        kv_save("today_pick", pick)
    return jsonify({"game": pick["game"]})

@app.route("/api/todays_game/reroll", methods=["POST"])
def reroll_game():
    games = kv_load("games", DEFAULT_GAMES)
    if not games:
        return jsonify({"game": None})
    pick = {"date": datetime.now().strftime("%Y-%m-%d"), "game": random.choice(games)}
    kv_save("today_pick", pick)
    return jsonify({"game": pick["game"]})

@app.route("/api/games", methods=["GET", "POST"])
def games():
    if request.method == "POST":
        data = request.get_json() or {}
        new_list = [g.strip() for g in data.get("games", []) if g and g.strip()]
        kv_save("games", new_list)
        return jsonify({"ok": True, "games": new_list})
    return jsonify({"games": kv_load("games", DEFAULT_GAMES)})

@app.route("/api/currently_playing", methods=["GET", "POST"])
def currently_playing():
    if request.method == "POST":
        data = request.get_json() or {}
        kv_save("currently_playing", {"game": data.get("game", ""), "doing": data.get("doing", "")})
        return jsonify({"ok": True})
    return jsonify(kv_load("currently_playing", DEFAULT_CURRENT))

def get_notes():
    notes = kv_load("notes", [])
    changed = False
    for i, n in enumerate(notes):
        if not n.get("id"):
            n["id"] = uuid.uuid4().hex[:8]
            changed = True
        if not n.get("color"):
            n["color"] = NOTE_COLORS[i % len(NOTE_COLORS)]
            changed = True
        n.setdefault("done", False)
    if changed:
        kv_save("notes", notes)
    return notes

@app.route("/api/notes", methods=["GET"])
def notes_list():
    return jsonify({"notes": get_notes()})

@app.route("/api/notes", methods=["POST"])
def notes_add():
    data = request.get_json() or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "Text required"}), 400
    notes = get_notes()
    color = data.get("color") if data.get("color") in NOTE_COLORS else NOTE_COLORS[len(notes) % len(NOTE_COLORS)]
    note = {"id": uuid.uuid4().hex[:8], "text": text, "color": color, "done": False}
    notes.append(note)
    kv_save("notes", notes)
    return jsonify({"ok": True, "note": note, "notes": notes})

@app.route("/api/notes/<note_id>", methods=["PATCH"])
def notes_update(note_id):
    data = request.get_json() or {}
    notes = get_notes()
    for n in notes:
        if n["id"] == note_id:
            if "text" in data:
                n["text"] = (data["text"] or "").strip()
            if "color" in data and data["color"] in NOTE_COLORS:
                n["color"] = data["color"]
            if "done" in data:
                n["done"] = bool(data["done"])
            break
    else:
        return jsonify({"ok": False, "error": "Not found"}), 404
    kv_save("notes", notes)
    return jsonify({"ok": True, "notes": notes})

@app.route("/api/notes/<note_id>", methods=["DELETE"])
def notes_delete(note_id):
    notes = [n for n in get_notes() if n["id"] != note_id]
    kv_save("notes", notes)
    return jsonify({"ok": True, "notes": notes})

@app.route("/api/quote")
def quote():
    try:
        r = requests.get("https://zenquotes.io/api/today", timeout=6)
        r.raise_for_status()
        item = r.json()[0]
        return jsonify({"quote": item.get("q", ""), "author": item.get("a", "")})
    except Exception:
        fallbacks = [("The best way to predict the future is to invent it.", "Alan Kay"),
                     ("Simplicity is the ultimate sophistication.", "Leonardo da Vinci"),
                     ("Stay hungry, stay foolish.", "Steve Jobs")]
        q, a = random.choice(fallbacks)
        return jsonify({"quote": q, "author": a, "fallback": True})

@app.route("/api/weather_config", methods=["GET", "POST"])
def weather_config():
    if request.method == "POST":
        data = request.get_json() or {}
        cfg = kv_load("weather_config", DEFAULT_WEATHER_CONFIG)
        if "lat" in data:
            try:
                cfg["lat"] = float(data["lat"])
            except (TypeError, ValueError):
                pass
        if "lon" in data:
            try:
                cfg["lon"] = float(data["lon"])
            except (TypeError, ValueError):
                pass
        if "name" in data and data["name"].strip():
            cfg["name"] = data["name"].strip()
        if "timezone" in data and data["timezone"].strip():
            cfg["timezone"] = data["timezone"].strip()
        kv_save("weather_config", cfg)
        return jsonify({"ok": True, **cfg})
    return jsonify(kv_load("weather_config", DEFAULT_WEATHER_CONFIG))

@app.route("/api/weather")
def weather():
    try:
        cfg = kv_load("weather_config", DEFAULT_WEATHER_CONFIG)
        lat = cfg.get("lat", DEFAULT_LAT)
        lon = cfg.get("lon", DEFAULT_LON)
        tz = cfg.get("timezone", DEFAULT_TIMEZONE)
        url = ("https://api.open-meteo.com/v1/forecast" + "?latitude=" + str(lat) + "&longitude=" + str(lon) + "&current=temperature_2m,weather_code,wind_speed_10m,relative_humidity_2m" + "&daily=temperature_2m_max,temperature_2m_min" + "&timezone=" + tz + "&forecast_days=1")
        r = requests.get(url, timeout=6)
        r.raise_for_status()
        d = r.json()
        cur = d.get("current", {})
        daily = d.get("daily", {})
        return jsonify({"temp": cur.get("temperature_2m"), "humidity": cur.get("relative_humidity_2m"), "wind": cur.get("wind_speed_10m"), "code": cur.get("weather_code"), "description": weather_code_to_text(cur.get("weather_code")), "high": (daily.get("temperature_2m_max") or [None])[0], "low": (daily.get("temperature_2m_min") or [None])[0], "location": cfg.get("name", DEFAULT_LOCATION_NAME)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def weather_code_to_text(code):
    mapping = {0: ("Clear sky", "sun"), 1: ("Mainly clear", "sun2"), 2: ("Partly cloudy", "cloud_sun"), 3: ("Overcast", "cloud"), 45: ("Foggy", "fog"), 48: ("Rime fog", "fog"), 51: ("Light drizzle", "drizzle"), 53: ("Drizzle", "drizzle"), 55: ("Heavy drizzle", "rain"), 61: ("Light rain", "drizzle"), 63: ("Rain", "rain"), 65: ("Heavy rain", "rain"), 71: ("Light snow", "snow_light"), 73: ("Snow", "snow"), 75: ("Heavy snow", "snow"), 77: ("Snow grains", "snow"), 80: ("Rain showers", "drizzle"), 81: ("Heavy showers", "rain"), 82: ("Violent showers", "storm"), 85: ("Snow showers", "snow_light"), 86: ("Heavy snow showers", "snow"), 95: ("Thunderstorm", "storm"), 96: ("Thunderstorm w/ hail", "storm"), 99: ("Heavy thunderstorm", "storm")}
    text, _ = mapping.get(code, ("Unknown", "?"))
    return text

def parse_iso_datetime(s):
    if not s:
        return None
    try:
        s = re.sub(r'\+(\d{2})(\d{2})$', r'+\1:\2', s)
        return datetime.fromisoformat(s)
    except Exception:
        return None

@app.route("/api/transport_config", methods=["GET", "POST"])
def transport_config():
    if request.method == "POST":
        data = request.get_json() or {}
        cfg = kv_load("transport", DEFAULT_TRANSPORT)
        for key in ("from_stop", "to_stop"):
            if key in data and data[key]:
                cfg[key] = data[key].strip()
        for key in ("walk_to_stop_min", "walk_from_stop_min"):
            if key in data:
                try:
                    cfg[key] = max(0, int(data[key]))
                except (TypeError, ValueError):
                    pass
        kv_save("transport", cfg)
        return jsonify({"ok": True, **cfg})
    return jsonify(kv_load("transport", DEFAULT_TRANSPORT))

@app.route("/api/transport")
def transport():
    try:
        cfg = kv_load("transport", DEFAULT_TRANSPORT)
        if not cfg.get("from_stop") or not cfg.get("to_stop"):
            return jsonify({"error": "Transport stops not configured", "from_stop": "", "to_stop": "", "walk_to_stop_min": cfg.get("walk_to_stop_min", 0), "walk_from_stop_min": cfg.get("walk_from_stop_min", 0), "connections": []})
        url = "http://transport.opendata.ch/v1/connections?from=" + cfg["from_stop"] + "&to=" + cfg["to_stop"] + "&limit=6"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        connections = r.json().get("connections", []) or []
        now = datetime.now().astimezone()
        walk_to = int(cfg.get("walk_to_stop_min", 0))
        walk_from = int(cfg.get("walk_from_stop_min", 0))
        results = []
        for c in connections:
            dep = c.get("from", {}).get("departure")
            arr = c.get("to", {}).get("arrival")
            if not dep:
                continue
            dep_dt = parse_iso_datetime(dep)
            arr_dt = parse_iso_datetime(arr) if arr else None
            if dep_dt is None:
                continue
            leave_home = dep_dt.timestamp() - walk_to * 60
            mins_until_leave = (leave_home - now.timestamp()) / 60
            mins_until_bus = (dep_dt.timestamp() - now.timestamp()) / 60
            total_door_to_door = None
            if arr_dt:
                total_door_to_door = int((arr_dt.timestamp() - leave_home) / 60 + walk_from)
            line = None
            sections = c.get("sections", []) or []
            if sections:
                j = sections[0].get("journey") or {}
                line = j.get("number") or j.get("category")
            results.append({"bus_line": line, "departure": dep_dt.strftime("%H:%M"), "arrival": arr_dt.strftime("%H:%M") if arr_dt else None, "departure_ts": dep_dt.timestamp(), "arrival_ts": arr_dt.timestamp() if arr_dt else None, "minutes_until_leave": round(mins_until_leave), "minutes_until_bus": round(mins_until_bus), "total_minutes": total_door_to_door})
        return jsonify({"from_stop": cfg["from_stop"], "to_stop": cfg["to_stop"], "walk_to_stop_min": walk_to, "walk_from_stop_min": walk_from, "connections": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    print("Dashboard running at http://localhost:" + str(port) + "  DB: " + DB_URL)
    app.run(host="0.0.0.0", port=port, debug=False)
