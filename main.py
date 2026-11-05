"""
Weather App - PM Accelerator AI Engineer Intern Technical Assessment #2 (Backend)
Author: Hocine Zair

Stack: Python, FastAPI, SQLite, Open-Meteo (weather + geocoding),
       OpenStreetMap Nominatim (zip codes / landmarks / reverse geocoding),
       Wikipedia REST API (extra info). No API keys required.
"""
import csv
import io
import json
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Optional
from urllib.parse import quote
from xml.etree import ElementTree as ET

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fpdf import FPDF
from pydantic import BaseModel

app = FastAPI(title="Weather App", description="Weather CRUD API by Hocine Zair")

# Allow the React frontend (Vite dev server) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

WEATHER_CODES = {
    0: "Clear sky", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Freezing fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    56: "Freezing drizzle", 57: "Heavy freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain",
    66: "Freezing rain", 67: "Heavy freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Light showers", 81: "Showers", 82: "Violent showers",
    85: "Snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Severe thunderstorm with hail",
}


def describe(code) -> str:
    return WEATHER_CODES.get(code, "Unknown")

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
NOMINATIM = "https://nominatim.openstreetmap.org"
HEADERS = {"User-Agent": "WeatherInternProject/1.0 (houcine.zair.07@gmail.com)"}
DB_FILE = "weather.db"
COORD_RE = re.compile(r"^\s*(-?\d{1,3}(?:\.\d+)?)\s*[,;\s]\s*(-?\d{1,3}(?:\.\d+)?)\s*$")

_nominatim_lock = threading.Lock()
_last_nominatim_time = 0.0
_location_cache = {}
_cache_lock = threading.Lock()


def _nominatim_get(path: str, params: dict) -> httpx.Response:
    """Make a request to Nominatim adhering to its usage policy (max 1 req/sec)."""
    global _last_nominatim_time
    with _nominatim_lock:
        elapsed = time.time() - _last_nominatim_time
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        resp = httpx.get(
            f"{NOMINATIM}{path}",
            params=params,
            headers=HEADERS,
            timeout=10,
        )
        _last_nominatim_time = time.time()
        return resp


# ---------------------------------------------------------------- Database
@contextmanager
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db():
    with get_db() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                location TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                temps TEXT NOT NULL,
                note TEXT DEFAULT ''
            )
            """
        )


init_db()


def row_to_dict(row) -> dict:
    rec = dict(row)
    rec["temps"] = json.loads(rec["temps"])
    return rec


# ----------------------------------------------------------------- Helpers
def find_location(query: str) -> dict:
    """Resolve user input (coordinates, city, town, zip code, landmark) to a real place."""
    query = query.strip()
    if not query:
        raise HTTPException(400, "Location cannot be empty.")

    cache_key = query.lower()
    with _cache_lock:
        if cache_key in _location_cache:
            return dict(_location_cache[cache_key])

    # 1) GPS coordinates, e.g. "35.69, -0.63"
    m = COORD_RE.match(query)
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise HTTPException(400, "Coordinates are out of range.")
        label = f"{lat}, {lon}"
        try:
            r = _nominatim_get(
                "/reverse",
                params={"lat": lat, "lon": lon, "format": "jsonv2"},
            )
            if r.status_code == 200:
                label = r.json().get("display_name", label)
        except httpx.HTTPError:
            pass  # label is cosmetic; continue with raw coordinates
        result = {"latitude": lat, "longitude": lon, "label": label}
        with _cache_lock:
            _location_cache[cache_key] = result
        return dict(result)

    # 2) Cities and towns (Open-Meteo geocoding, handles fuzzy matches)
    try:
        r = httpx.get(GEOCODE_URL, params={"name": query, "count": 1}, timeout=10)
        r.raise_for_status()
        results = r.json().get("results")
    except httpx.HTTPError:
        raise HTTPException(502, "Location service is unavailable, try again later.")
    if results:
        p = results[0]
        label = ", ".join(x for x in [p.get("name"), p.get("admin1"), p.get("country")] if x)
        result = {"latitude": p["latitude"], "longitude": p["longitude"], "label": label}
        with _cache_lock:
            _location_cache[cache_key] = result
        return dict(result)

    # 3) Fallback: zip/postal codes, landmarks, addresses (OpenStreetMap)
    try:
        r = _nominatim_get(
            "/search",
            params={"q": query, "format": "jsonv2", "limit": 1},
        )
        r.raise_for_status()
        hits = r.json()
    except httpx.HTTPError:
        raise HTTPException(502, "Location service is unavailable, try again later.")
    if not hits:
        raise HTTPException(404, f"Could not find a location called '{query}'.")
    h = hits[0]
    result = {"latitude": float(h["lat"]), "longitude": float(h["lon"]), "label": h["display_name"]}
    with _cache_lock:
        _location_cache[cache_key] = result
    return dict(result)


def validate_dates(start: date, end: date):
    today = date.today()
    if end < start:
        raise HTTPException(400, "end_date cannot be before start_date.")
    if (end - start).days > 30:
        raise HTTPException(400, "Date range cannot be longer than 31 days.")
    if start < today - timedelta(days=90) or end > today + timedelta(days=15):
        raise HTTPException(
            400, "Dates must be within the last 90 days and the next 15 days."
        )


def fetch_daily_temps(lat: float, lon: float, start: date, end: date) -> list:
    try:
        r = httpx.get(
            FORECAST_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": "temperature_2m_max,temperature_2m_min",
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "timezone": "auto",
            },
            timeout=10,
        )
        r.raise_for_status()
    except httpx.HTTPError:
        raise HTTPException(502, "Weather service is unavailable, try again later.")
    d = r.json()["daily"]
    return [
        {"date": t, "max": mx, "min": mn}
        for t, mx, mn in zip(d["time"], d["temperature_2m_max"], d["temperature_2m_min"])
    ]


# ------------------------------------------------------------------ Models
class RecordIn(BaseModel):
    location: str
    start_date: date
    end_date: date


class RecordUpdate(BaseModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    note: Optional[str] = None


# --------------------------------------------------------- Current weather
@app.get("/weather")
def current_weather(location: str):
    place = find_location(location)
    try:
        r = httpx.get(
            FORECAST_URL,
            params={
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
                "timezone": "auto",
            },
            timeout=10,
        )
        r.raise_for_status()
    except httpx.HTTPError:
        raise HTTPException(502, "Weather service is unavailable, try again later.")
    current = r.json()["current"]
    current["description"] = describe(current.get("weather_code"))
    return {
        "location": place["label"],
        "latitude": place["latitude"],
        "longitude": place["longitude"],
        "current": current,
    }


@app.get("/forecast")
def five_day_forecast(location: str):
    """5-day forecast for any location input (city, zip, landmark, coordinates)."""
    place = find_location(location)
    try:
        r = httpx.get(
            FORECAST_URL,
            params={
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "forecast_days": 5,
                "timezone": "auto",
            },
            timeout=10,
        )
        r.raise_for_status()
    except httpx.HTTPError:
        raise HTTPException(502, "Weather service is unavailable, try again later.")
    d = r.json()["daily"]
    days = []
    for i, day in enumerate(d["time"]):
        days.append({
            "date": day,
            "weather_code": d["weather_code"][i],
            "description": describe(d["weather_code"][i]),
            "max": d["temperature_2m_max"][i],
            "min": d["temperature_2m_min"][i],
            "rain_chance": d["precipitation_probability_max"][i],
        })
    return {"location": place["label"], "days": days}


# -------------------------------------------------------------------- CRUD
@app.post("/records", status_code=201)
def create_record(body: RecordIn):
    validate_dates(body.start_date, body.end_date)
    place = find_location(body.location)
    temps = fetch_daily_temps(
        place["latitude"], place["longitude"], body.start_date, body.end_date
    )
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO records (location, latitude, longitude, start_date, end_date, temps) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                place["label"],
                place["latitude"],
                place["longitude"],
                body.start_date.isoformat(),
                body.end_date.isoformat(),
                json.dumps(temps),
            ),
        )
        row = db.execute("SELECT * FROM records WHERE id = ?", (cur.lastrowid,)).fetchone()
    return row_to_dict(row)


@app.get("/records")
def list_records():
    with get_db() as db:
        rows = db.execute("SELECT * FROM records ORDER BY id DESC").fetchall()
    return [row_to_dict(r) for r in rows]


@app.get("/records/{record_id}")
def get_record(record_id: int):
    with get_db() as db:
        row = db.execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Record not found.")
    return row_to_dict(row)


@app.put("/records/{record_id}")
def update_record(record_id: int, body: RecordUpdate):
    with get_db() as db:
        row = db.execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Record not found.")

        if body.start_date is not None or body.end_date is not None:
            start = body.start_date or date.fromisoformat(row["start_date"])
            end = body.end_date or date.fromisoformat(row["end_date"])
            validate_dates(start, end)
            # Re-fetch temperatures so stored data matches the updated dates
            temps = fetch_daily_temps(row["latitude"], row["longitude"], start, end)
            temps_json = json.dumps(temps)
        else:
            start = date.fromisoformat(row["start_date"])
            end = date.fromisoformat(row["end_date"])
            temps_json = row["temps"]

        note = body.note if body.note is not None else row["note"]
        db.execute(
            "UPDATE records SET start_date=?, end_date=?, temps=?, note=? WHERE id=?",
            (start.isoformat(), end.isoformat(), temps_json, note, record_id),
        )
        row = db.execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()
    return row_to_dict(row)


@app.delete("/records/{record_id}")
def delete_record(record_id: int):
    with get_db() as db:
        cur = db.execute("DELETE FROM records WHERE id = ?", (record_id,))
    if cur.rowcount == 0:
        raise HTTPException(404, "Record not found.")
    return {"deleted": record_id}


# ------------------------------------------------------------------ Export
@app.get("/export/{fmt}")
def export_records(fmt: str):
    with get_db() as db:
        rows = db.execute("SELECT * FROM records ORDER BY id").fetchall()
    records = [row_to_dict(r) for r in rows]

    if fmt == "json":
        return Response(
            json.dumps(records, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=weather.json"},
        )

    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["id", "location", "date", "max_temp", "min_temp", "note"])
        for rec in records:
            for t in rec["temps"]:
                w.writerow([rec["id"], rec["location"], t["date"], t["max"], t["min"], rec["note"]])
        return Response(
            buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=weather.csv"},
        )

    if fmt == "xml":
        root = ET.Element("records")
        for rec in records:
            e = ET.SubElement(root, "record", id=str(rec["id"]))
            for k in ("location", "latitude", "longitude", "start_date", "end_date", "note"):
                ET.SubElement(e, k).text = str(rec[k])
            temps = ET.SubElement(e, "temps")
            for t in rec["temps"]:
                ET.SubElement(
                    temps, "day", date=t["date"], max=str(t["max"]), min=str(t["min"])
                )
        return Response(
            ET.tostring(root, encoding="unicode"),
            media_type="application/xml",
            headers={"Content-Disposition": "attachment; filename=weather.xml"},
        )

    if fmt == "md":
        lines = ["# Weather Records", ""]
        for rec in records:
            lines.append(f"## {rec['location']} ({rec['start_date']} to {rec['end_date']})")
            if rec["note"]:
                lines.append(f"*{rec['note']}*")
            lines += ["", "| Date | Max C | Min C |", "|---|---|---|"]
            lines += [f"| {t['date']} | {t['max']} | {t['min']} |" for t in rec["temps"]]
            lines.append("")
        return Response(
            "\n".join(lines),
            media_type="text/markdown",
            headers={"Content-Disposition": "attachment; filename=weather.md"},
        )

    if fmt == "pdf":
        def clean(text) -> str:
            # built-in PDF fonts only support latin-1 characters
            return str(text).encode("latin-1", "replace").decode("latin-1")

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 10, "Weather Records", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", size=10)
        pdf.cell(0, 6, "Generated by Hocine Zair's Weather App", new_x="LMARGIN", new_y="NEXT")
        for rec in records:
            pdf.ln(4)
            pdf.set_font("Helvetica", "B", 11)
            pdf.multi_cell(0, 6, clean(f"#{rec['id']} {rec['location']}"), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", size=10)
            pdf.cell(0, 5, clean(f"{rec['start_date']} to {rec['end_date']}"), new_x="LMARGIN", new_y="NEXT")
            if rec.get("note"):
                pdf.multi_cell(0, 5, clean(f"Note: {rec['note']}"), new_x="LMARGIN", new_y="NEXT")
            for t in rec.get("temps", []):
                pdf.cell(0, 5, clean(f"  {t['date']}:  max {t['max']} C   min {t['min']} C"),
                         new_x="LMARGIN", new_y="NEXT")
        return Response(
            bytes(pdf.output()),
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=weather.pdf"},
        )

    raise HTTPException(400, "Format must be json, csv, xml, pdf or md.")


# --------------------------------------------------------- Extra API usage
@app.get("/records/{record_id}/extras")
def record_extras(record_id: int):
    rec = get_record(record_id)
    city = rec["location"].split(",")[0].strip()
    map_link = f"https://www.google.com/maps?q={rec['latitude']},{rec['longitude']}"

    summary = None
    try:
        r = httpx.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(city, safe='')}",
            headers=HEADERS,
            timeout=10,
            follow_redirects=True,
        )
        if r.status_code == 200:
            summary = r.json().get("extract")
    except httpx.HTTPError:
        pass  # extras are optional; never fail the request because of them

    return {
        "google_maps_link": map_link,
        "youtube_search_link": f"https://www.youtube.com/results?search_query={quote(city + ' travel')}",
        "wikipedia_summary": summary,
    }


# -------------------------------------------------------------- Home page
@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html><head><title>Weather App</title></head>
    <body style="font-family: sans-serif; max-width: 700px; margin: 40px auto;">
      <h1>Weather App</h1>
      <p>Built by <b>Hocine Zair</b> for the PM Accelerator AI Engineer Intern
      technical assessment (Assessment #2, backend).</p>
      <h3>About PM Accelerator</h3>
      <p>PM Accelerator is a US-based company with a global reach, focused on AI
      learning and acting as a development hub for AI products. It offers an
      AI PM Bootcamp with hands-on experience, mentorship from professionals at
      top tech companies, and real-world projects.</p>
      <h3>Try it</h3>
      <ul>
        <li><a href="/docs">Interactive API docs (Swagger UI)</a></li>
        <li><a href="/weather?location=Oran">Current weather: Oran</a></li>
        <li><a href="/records">All saved records</a></li>
        <li>Export: <a href="/export/json">JSON</a> |
            <a href="/export/csv">CSV</a> |
            <a href="/export/xml">XML</a> |
            <a href="/export/pdf">PDF</a> |
            <a href="/export/md">Markdown</a></li>
      </ul>
    </body></html>
    """
