// Base URL of the FastAPI backend. Override with VITE_API_URL if needed.
export const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

// Small fetch wrapper that turns every failure into a readable Error message.
export async function api(path, options = {}) {
  const init = { ...options };
  if (options.body) {
    init.headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  }

  let res;
  try {
    res = await fetch(API_URL + path, init);
  } catch {
    throw new Error(
      `Can't reach the weather server at ${API_URL}. Start the backend and try again.`
    );
  }

  let data = null;
  try {
    data = await res.json();
  } catch {
    /* response had no JSON body */
  }

  if (!res.ok) {
    let msg = data && data.detail;
    if (Array.isArray(msg)) msg = msg.map((m) => m.msg).join("; ");
    throw new Error(msg || `Request failed (${res.status}).`);
  }
  return data;
}
