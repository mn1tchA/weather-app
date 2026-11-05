import { useEffect, useState } from "react";
import { api, API_URL } from "./api.js";
import "./App.css";

/* ---------- helpers ---------- */
function iconFor(code) {
  if (code === 0) return "☀️";
  if (code === 1) return "🌤️";
  if (code === 2) return "⛅";
  if (code === 3) return "☁️";
  if (code === 45 || code === 48) return "🌫️";
  if (code >= 51 && code <= 57) return "🌦️";
  if (code >= 61 && code <= 67) return "🌧️";
  if (code >= 71 && code <= 77) return "❄️";
  if (code >= 80 && code <= 82) return "🌧️";
  if (code === 85 || code === 86) return "🌨️";
  if (code >= 95) return "⛈️";
  return "🌡️";
}

function isoDay(offset) {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function dayName(iso, index) {
  if (index === 0) return "Today";
  return new Date(iso + "T12:00:00").toLocaleDateString(undefined, { weekday: "short" });
}

function shortDate(iso) {
  return new Date(iso + "T12:00:00").toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

const EXPORT_FORMATS = ["json", "csv", "xml", "pdf", "md"];

/* ---------- current weather ---------- */
function CurrentWeather({ place, current }) {
  return (
    <section className="current" aria-label="Current weather">
      <div className="current-main">
        <p className="place">{place}</p>
        <p className="temp">
          {Math.round(current.temperature_2m)}
          <span className="deg">°C</span>
        </p>
        <p className="condition">{current.description}</p>
      </div>
      <div className="current-side">
        <span className="big-icon" role="img" aria-label={current.description}>
          {iconFor(current.weather_code)}
        </span>
        <dl className="facts">
          <div>
            <dt>Humidity</dt>
            <dd>{current.relative_humidity_2m}%</dd>
          </div>
          <div>
            <dt>Wind</dt>
            <dd>{current.wind_speed_10m} km/h</dd>
          </div>
          <div>
            <dt>Local time</dt>
            <dd>{current.time.replace("T", " ")}</dd>
          </div>
        </dl>
      </div>
    </section>
  );
}

/* ---------- 5-day forecast ---------- */
function Forecast({ days }) {
  const lo = Math.min(...days.map((d) => d.min));
  const hi = Math.max(...days.map((d) => d.max));
  const span = hi - lo || 1;

  return (
    <section aria-label="Five-day forecast">
      <h2>Next 5 days</h2>
      <ol className="forecast">
        {days.map((d, i) => (
          <li key={d.date} className="day">
            <p className="day-name">{dayName(d.date, i)}</p>
            <p className="day-date">{shortDate(d.date)}</p>
            <span className="day-icon" role="img" aria-label={d.description}>
              {iconFor(d.weather_code)}
            </span>
            <p className="day-desc">{d.description}</p>
            <div
              className="range"
              role="img"
              aria-label={`Low ${Math.round(d.min)}, high ${Math.round(d.max)} degrees`}
            >
              <span
                className="range-bar"
                style={{
                  left: `${((d.min - lo) / span) * 100}%`,
                  width: `${Math.max(((d.max - d.min) / span) * 100, 6)}%`,
                }}
              />
            </div>
            <p className="day-temps">
              <strong>{Math.round(d.max)}°</strong> <span>{Math.round(d.min)}°</span>
            </p>
            <p className="day-rain">
              {d.rain_chance == null ? "" : `${d.rain_chance}% rain`}
            </p>
          </li>
        ))}
      </ol>
    </section>
  );
}

/* ---------- one saved record ---------- */
function RecordCard({ rec, onChanged, onError }) {
  const [note, setNote] = useState(rec.note || "");
  const [open, setOpen] = useState(false);
  const [extras, setExtras] = useState(null);
  const [busy, setBusy] = useState(false);

  async function run(fn) {
    setBusy(true);
    onError("");
    try {
      await fn();
    } catch (e) {
      onError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const saveNote = () =>
    run(async () => {
      await api(`/records/${rec.id}`, {
        method: "PUT",
        body: JSON.stringify({ note }),
      });
      await onChanged();
    });

  const remove = () =>
    run(async () => {
      await api(`/records/${rec.id}`, { method: "DELETE" });
      await onChanged();
    });

  const loadExtras = () =>
    run(async () => {
      setExtras(await api(`/records/${rec.id}/extras`));
    });

  return (
    <li className="record">
      <div className="record-head">
        <div>
          <h3>{rec.location}</h3>
          <p className="muted">
            {shortDate(rec.start_date)} to {shortDate(rec.end_date)}
          </p>
        </div>
        <button className="link-btn" onClick={() => setOpen(!open)} aria-expanded={open}>
          {open ? "Hide temperatures" : "Show temperatures"}
        </button>
      </div>

      {open && (
        <table className="temps">
          <thead>
            <tr>
              <th scope="col">Date</th>
              <th scope="col">High</th>
              <th scope="col">Low</th>
            </tr>
          </thead>
          <tbody>
            {rec.temps.map((t) => (
              <tr key={t.date}>
                <td>{shortDate(t.date)}</td>
                <td>{t.max}°C</td>
                <td>{t.min}°C</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="note-row">
        <label htmlFor={`note-${rec.id}`} className="sr-only">
          Note for {rec.location}
        </label>
        <input
          id={`note-${rec.id}`}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Add a note"
        />
        <button onClick={saveNote} disabled={busy}>
          Save note
        </button>
        <button onClick={loadExtras} disabled={busy} className="secondary">
          Place info
        </button>
        <button onClick={remove} disabled={busy} className="danger">
          Delete
        </button>
      </div>

      {extras && (
        <div className="extras">
          {extras.wikipedia_summary && <p>{extras.wikipedia_summary}</p>}
          <p>
            <a href={extras.google_maps_link} target="_blank" rel="noreferrer">
              Open in Google Maps
            </a>
            {"  "}
            <a href={extras.youtube_search_link} target="_blank" rel="noreferrer">
              Find videos on YouTube
            </a>
          </p>
        </div>
      )}
    </li>
  );
}

/* ---------- app ---------- */
export default function App() {
  const [query, setQuery] = useState("");
  const [current, setCurrent] = useState(null);
  const [place, setPlace] = useState("");
  const [days, setDays] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [records, setRecords] = useState([]);
  const [recordsError, setRecordsError] = useState("");
  const [startDate, setStartDate] = useState(isoDay(-4));
  const [endDate, setEndDate] = useState(isoDay(0));
  const [saving, setSaving] = useState(false);

  async function loadRecords() {
    try {
      setRecords(await api("/records"));
      setRecordsError("");
    } catch (e) {
      setRecordsError(e.message);
    }
  }

  useEffect(() => {
    loadRecords();
  }, []);

  async function search(q) {
    const text = (q ?? query).trim();
    if (!text) {
      setError("Enter a city, zip code, landmark or coordinates first.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const enc = encodeURIComponent(text);
      const [now, fc] = await Promise.all([
        api(`/weather?location=${enc}`),
        api(`/forecast?location=${enc}`),
      ]);
      setCurrent(now.current);
      setPlace(now.location);
      setDays(fc.days);
    } catch (e) {
      setCurrent(null);
      setDays(null);
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  function useMyLocation() {
    if (!navigator.geolocation) {
      setError("This browser can't share your location. Type a place instead.");
      return;
    }
    setLoading(true);
    setError("");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const q = `${pos.coords.latitude.toFixed(4)}, ${pos.coords.longitude.toFixed(4)}`;
        setQuery(q);
        search(q);
      },
      () => {
        setLoading(false);
        setError("Location access was blocked. Allow it in your browser or type a place instead.");
      }
    );
  }

  async function saveRecord(e) {
    e.preventDefault();
    if (!query.trim()) {
      setRecordsError("Search for a place first, then choose the dates to save.");
      return;
    }
    setSaving(true);
    setRecordsError("");
    try {
      await api("/records", {
        method: "POST",
        body: JSON.stringify({ location: query.trim(), start_date: startDate, end_date: endDate }),
      });
      await loadRecords();
    } catch (err) {
      setRecordsError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page">
      <header className="top">
        <h1>Weather</h1>
        <p className="lede">Check conditions at home or at the place you're heading to.</p>

        <form
          className="search"
          onSubmit={(e) => {
            e.preventDefault();
            search();
          }}
        >
          <label htmlFor="q" className="sr-only">
            Location
          </label>
          <input
            id="q"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="City, zip code, landmark or 35.69, -0.63"
            autoComplete="off"
          />
          <button type="submit" disabled={loading}>
            {loading ? "Searching…" : "Search"}
          </button>
          <button type="button" className="secondary" onClick={useMyLocation} disabled={loading}>
            Use my location
          </button>
        </form>

        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </header>

      <main>
        {current && <CurrentWeather place={place} current={current} />}
        {days && <Forecast days={days} />}
        {!current && !error && !loading && (
          <p className="empty">Search for a place to see the weather right now and the next five days.</p>
        )}

        <section className="saved" aria-label="Saved weather records">
          <h2>Saved date ranges</h2>
          <p className="muted">
            Save the daily highs and lows for the place in the search box. Dates can be up to 90
            days back and 15 days ahead, within a 31-day range.
          </p>

          <form className="save-form" onSubmit={saveRecord}>
            <label>
              From
              <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} required />
            </label>
            <label>
              To
              <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} required />
            </label>
            <button type="submit" disabled={saving}>
              {saving ? "Saving…" : "Save range"}
            </button>
          </form>

          {recordsError && (
            <p className="error" role="alert">
              {recordsError}
            </p>
          )}

          {records.length === 0 && !recordsError ? (
            <p className="empty">Nothing saved yet. Pick a place and a date range above.</p>
          ) : (
            <ul className="records">
              {records.map((r) => (
                <RecordCard key={r.id} rec={r} onChanged={loadRecords} onError={setRecordsError} />
              ))}
            </ul>
          )}

          <p className="exports">
            Export all records:{" "}
            {EXPORT_FORMATS.map((f) => (
              <a key={f} href={`${API_URL}/export/${f}`} target="_blank" rel="noreferrer">
                {f.toUpperCase()}
              </a>
            ))}
          </p>
        </section>
      </main>

      <footer>
        <p>
          Built by <strong>Hocine Zair</strong> for the PM Accelerator AI Engineer Intern technical
          assessment (Assessment #1 frontend and #2 backend).
        </p>
        <p>
          PM Accelerator is a US-based company with a global reach, focused on AI learning and
          acting as a development hub for AI products. It offers an AI PM Bootcamp with hands-on
          experience, mentorship from professionals at top tech companies, and real-world projects.
        </p>
      </footer>
    </div>
  );
}
