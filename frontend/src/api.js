// frontend/src/api.js
const defaultBase =
  typeof window !== "undefined" && window.location?.origin
    ? window.location.origin
    : "http://localhost:8000";

const runtimeBackendBase =
  typeof window !== "undefined" && window.__BACKEND_URL__
    ? window.__BACKEND_URL__
    : null;

export const API_BASE = runtimeBackendBase || defaultBase;

async function readErrorMessage(res, fallback = "Request failed") {
  try {
    const contentType = res.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      const data = await res.json();
      return data?.detail || data?.message || fallback;
    }
    const text = await res.text();
    return text || fallback;
  } catch {
    return fallback;
  }
}

export const ENDPOINTS = {
  HEALTH: `${API_BASE}/api/health`,

  // Upload job system
  UPLOAD: `${API_BASE}/api/upload`,
  UPLOAD_BATCH: `${API_BASE}/api/upload/batch`,
  UPLOAD_STATUS: (id) => `${API_BASE}/api/upload/status/${id}`,
  UPLOAD_CANCEL: (id) => `${API_BASE}/api/upload/cancel/${id}`,
  UPLOAD_DELETE: (id) => `${API_BASE}/api/upload/${id}`,

  // Ask endpoints
  ASK: `${API_BASE}/api/ask`,
  ASK_STREAM: `${API_BASE}/api/ask/stream`,

  AUTH_CONFIG: `${API_BASE}/api/auth/config`,
  AUTH_REGISTER: `${API_BASE}/api/auth/register`,
  AUTH_LOGIN: `${API_BASE}/api/auth/login`,
  AUTH_GOOGLE: `${API_BASE}/api/auth/google`,
  AUTH_ME: `${API_BASE}/api/auth/me`,
  CHAT_HISTORY: `${API_BASE}/api/chat-history`,

  // NEW: Retrieve full text for citations
  SOURCE: (docId) => `${API_BASE}/api/source/${encodeURIComponent(docId)}`,
  PDF: (docId) => `${API_BASE}/api/pdf/${encodeURIComponent(docId)}`,
};

/* Health */
export async function health() {
  const res = await fetch(ENDPOINTS.HEALTH);
  if (!res.ok) throw new Error("Backend offline");
  return res.json();
}

function authHeaders(token) {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/* Upload APIs (unchanged) */
export async function startUpload(file, { signal, token } = {}) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(ENDPOINTS.UPLOAD, {
    method: "POST",
    body: form,
    signal,
    headers: authHeaders(token),
  });
  if (!res.ok) throw new Error(await readErrorMessage(res, "Upload failed"));
  const json = await res.json();
  try {
    if (json?.job_id) localStorage.setItem("last_upload_job_id", json.job_id);
  } catch (_) {}
  return json;
}

export async function startBatchUpload(files, { signal, token } = {}) {
  const form = new FormData();
  Array.from(files || []).forEach((file) => form.append("files", file));
  const res = await fetch(ENDPOINTS.UPLOAD_BATCH, {
    method: "POST",
    body: form,
    signal,
    headers: authHeaders(token),
  });
  if (!res.ok) throw new Error(await readErrorMessage(res, "Upload failed"));
  const json = await res.json();
  try {
    if (json?.job_id) localStorage.setItem("last_upload_job_id", json.job_id);
  } catch (_) {}
  return json;
}

export async function getUploadStatus(jobId, token) {
  const res = await fetch(ENDPOINTS.UPLOAD_STATUS(jobId), { headers: authHeaders(token) });
  if (res.status === 404) {
    const err = new Error("404: Job not found");
    err.code = 404;
    throw err;
  }
  if (!res.ok) throw new Error(await readErrorMessage(res, "Failed to fetch upload status"));
  return res.json();
}

export async function fetchUploadStatusRaw(jobId, token) {
  const res = await fetch(ENDPOINTS.UPLOAD_STATUS(jobId), { headers: authHeaders(token) });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(await readErrorMessage(res, "Failed to fetch upload status"));
  return res.json();
}

export async function cancelUpload(jobId, token) {
  const res = await fetch(ENDPOINTS.UPLOAD_CANCEL(jobId), {
    method: "POST",
    headers: authHeaders(token),
  });
  if (!res.ok) throw new Error(await readErrorMessage(res, "Failed to cancel upload"));
  return res.json();
}

export async function deleteUpload(jobId, token) {
  const res = await fetch(ENDPOINTS.UPLOAD_DELETE(jobId), {
    method: "DELETE",
    headers: authHeaders(token),
  });
  if (!res.ok) throw new Error(await readErrorMessage(res, "Failed to delete upload"));
  localStorage.removeItem("last_upload_job_id");
  return res.json();
}

/* ASK (non-streaming) */
export async function askQuestion(question, mode = "basic", token) {
  const form = new FormData();
  form.append("question", question);
  form.append("mode", mode);
  const res = await fetch(ENDPOINTS.ASK, {
    method: "POST",
    body: form,
    headers: authHeaders(token),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getAuthConfig() {
  const res = await fetch(ENDPOINTS.AUTH_CONFIG);
  if (!res.ok) throw new Error("Failed to load auth config");
  return res.json();
}

export async function registerUser({ name, email, password }) {
  const res = await fetch(ENDPOINTS.AUTH_REGISTER, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, email, password }),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail || "Registration failed");
  return res.json();
}

export async function loginUser({ email, password }) {
  const res = await fetch(ENDPOINTS.AUTH_LOGIN, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail || "Login failed");
  return res.json();
}

export async function loginWithGoogle(credential) {
  const res = await fetch(ENDPOINTS.AUTH_GOOGLE, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ credential }),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail || "Google login failed");
  return res.json();
}

export async function getCurrentUser(token) {
  const res = await fetch(ENDPOINTS.AUTH_ME, { headers: authHeaders(token) });
  if (!res.ok) throw new Error("Session expired");
  return res.json();
}

export async function getChatHistory(token) {
  const res = await fetch(ENDPOINTS.CHAT_HISTORY, { headers: authHeaders(token) });
  if (!res.ok) throw new Error("Failed to load chat history");
  return res.json();
}

export async function saveChatHistory(token, messages) {
  const res = await fetch(ENDPOINTS.CHAT_HISTORY, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ messages }),
  });
  if (!res.ok) throw new Error("Failed to save chat history");
  return res.json();
}

/* ASK STREAM */
export async function askStream(question, mode = "basic", { signal, token } = {}) {
  const res = await fetch(ENDPOINTS.ASK_STREAM, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ question, mode }),
    signal,
  });
  if (!res.ok) throw new Error(await res.text());
  return res;
}

/* NEW: Fetch full text for a given doc_id */
export async function fetchSource(docId, token) {
  if (!docId) throw new Error("docId required");
  const res = await fetch(ENDPOINTS.SOURCE(docId), { headers: authHeaders(token) });
  if (res.status === 404) throw new Error("Source not found");
  if (!res.ok) throw new Error("Failed to fetch source");
  return res.json(); // { doc_id, text }
}

export async function fetchSourcePdf(docId, token) {
  if (!docId) throw new Error("docId required");
  const res = await fetch(ENDPOINTS.PDF(docId), { headers: authHeaders(token) });
  if (res.status === 404) throw new Error("PDF source not found");
  if (!res.ok) throw new Error(await readErrorMessage(res, "Failed to fetch PDF source"));
  return res.blob();
}

/* Upload polling (unchanged) */
function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

function defaultBackoff(attempt, base = 300, cap = 5000) {
  const exp = Math.min(cap, Math.round(base * Math.pow(1.8, attempt)));
  const jitter = (Math.random() * 0.4 - 0.2) * exp;
  return Math.max(50, Math.round(exp + jitter));
}

export async function pollUploadStatus(
  jobId,
  {
    token,
    onUpdate = () => {},
    maxAttempts = 20,
    allow404Retries = 6,
    stopWhen = (job) => job && ["completed", "error", "canceled"].includes(job.status),
  } = {}
) {
  let attempt = 0, notFound = 0, last = null;
  while (attempt < maxAttempts) {
    try {
      const job = await fetchUploadStatusRaw(jobId, token);
      last = job;
      onUpdate(job);
      if (stopWhen(job)) {
        if (job && ["completed", "error", "canceled"].includes(job.status)) {
          localStorage.removeItem("last_upload_job_id");
        }
        return job;
      }
      if (job === null) {
        notFound++;
        if (notFound > allow404Retries) return null;
      } else notFound = 0;
    } catch (err) {
      console.warn("pollUploadStatus: transient error", err);
    }
    await sleep(defaultBackoff(attempt));
    attempt++;
  }
  return last;
}

export function resumeLastUploadPolling(opts = {}) {
  const jobId = localStorage.getItem("last_upload_job_id");
  if (!jobId) return null;
  return pollUploadStatus(jobId, opts);
}
