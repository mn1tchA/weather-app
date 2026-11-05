# Weather App (PM Accelerator AI Engineer Intern - Assessments #1 Frontend and #2 Backend)

Built by **Hocine Zair**.

A FastAPI backend that takes a location and a date range, validates both, pulls real
weather data from public APIs, stores it in SQLite, and supports full CRUD, data export
and extra API enrichment.

## About PM Accelerator
PM Accelerator is a US-based company with a global reach, focused on AI learning and acting
as a development hub for AI products. It offers an AI PM Bootcamp with hands-on experience,
mentorship from professionals at top tech companies, and real-world projects.

## Tech stack
- Backend: Python 3.9+, FastAPI, Uvicorn, httpx, fpdf2 (PDF export)
- Frontend: React 18 + Vite (JavaScript), plain CSS, responsive
- SQLite (built-in `sqlite3`)
- Open-Meteo (weather and geocoding), OpenStreetMap Nominatim (zip codes, landmarks,
  reverse geocoding), Wikipedia REST API. No API keys needed.

## Run the backend
```bash
git clone <your-repo-url>
cd <repo-folder>
python -m venv venv
# Windows: venv\Scripts\activate    Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```
Open http://127.0.0.1:8000/ (home page) or http://127.0.0.1:8000/docs (interactive API docs).

## Run the frontend (needs Node 18+)
In a second terminal, with the backend running:
```bash
cd frontend
npm install
npm run dev
```
Open the URL Vite prints (http://localhost:5173). To point at a different backend, set
`VITE_API_URL` (default `http://127.0.0.1:8000`).

**Frontend features (Assessment #1):** search by city, zip code, landmark or coordinates; current
weather with icons, humidity, wind and local time; "Use my location" (browser geolocation);
5-day forecast with temperature range bars and rain chance; clear error messages (location not
found, bad dates, server unreachable, location permission blocked); responsive layout for desktop,
tablet and phone; UI for saving, viewing, editing notes, deleting and exporting records.

## Features
**Location input** - city or town, zip/postal code, landmark, address, or GPS coordinates
(e.g. `35.69, -0.63`). Unknown locations return a clear 404 message.

**Current weather** - `GET /weather?location=Oran` (temperature, humidity, wind, description,
in the location's local time).

**5-day forecast** - `GET /forecast?location=Oran`.

**CRUD (SQLite)**
| Method | Endpoint | What it does |
|---|---|---|
| POST | `/records` | Create: location + date range, validated, daily min/max temperatures stored |
| GET | `/records` | Read all saved records |
| GET | `/records/{id}` | Read one record |
| PUT | `/records/{id}` | Update dates and/or note (temperatures are re-fetched so data stays consistent) |
| DELETE | `/records/{id}` | Delete a record |

**Validation** - end date not before start date, range of at most 31 days, dates within the
last 90 days to the next 15 days (the range the weather API supports), location must exist.

**Export** - `GET /export/json`, `/export/csv`, `/export/xml`, `/export/pdf`, `/export/md`.

**Extra API integration** - `GET /records/{id}/extras` returns a Google Maps link, a YouTube
search link and a Wikipedia summary for the location.

**Error handling** - invalid location (404), invalid dates (400), external API failures (502).

## Example request
```json
POST /records
{"location": "Oran", "start_date": "2026-11-01", "end_date": "2026-11-05"}
```

## Assessments completed
Tech Assessment #1 (Frontend) and Tech Assessment #2 (Backend): full stack.
