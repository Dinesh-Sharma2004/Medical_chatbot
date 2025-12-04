export const API_BASE = " https://medical-chatbot-1-pmsp.onrender.com";

export const ENDPOINTS = {
  HEALTH: `${API_BASE}/api/health`,

  UPLOAD: `${API_BASE}/api/upload`,
  UPLOAD_STATUS: (id) => `${API_BASE}/api/upload/status/${id}`,
  UPLOAD_CANCEL: (id) => `${API_BASE}/api/upload/cancel/${id}`,
  UPLOAD_DELETE: (id) => `${API_BASE}/api/upload/${id}`,

  ASK: `${API_BASE}/api/ask`,
  ASK_STREAM: `${API_BASE}/api/ask/stream`,
  SOURCE: (docId) => `${API_BASE}/api/source/${encodeURIComponent(docId)}`,
};

export async function health() {
  const res = await fetch(ENDPOINTS.HEALTH);
  if (!res.ok) throw new Error("Backend offline");
  return res.json();
}

export async function startUpload(file, { signal } = {}) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(ENDPOINTS.UPLOAD, { method: "POST", body: form, signal });
  if (!res.ok) throw new Error(await res.text());
  const json = await res.json();
  try {
    if (json?.job_id) localStorage.setItem("last_upload_job_id", json.job_id);
  } catch (_) {}
  return json;
}

export async function getUploadStatus(jobId) {
  const res = await fetch(ENDPOINTS.UPLOAD_STATUS(jobId));
  if (res.status === 404) {
    const err = new Error("404: Job not found");
    err.code = 404;
    throw err;
  }
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchUploadStatusRaw(jobId) {
  const res = await fetch(ENDPOINTS.UPLOAD_STATUS(jobId));
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function cancelUpload(jobId) {
  const res = await fetch(ENDPOINTS.UPLOAD_CANCEL(jobId), { method: "POST" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function deleteUpload(jobId) {
  const res = await fetch(ENDPOINTS.UPLOAD_DELETE(jobId), { method: "DELETE" });
  if (!res.ok) throw new Error(await res.text());
  localStorage.removeItem("last_upload_job_id");
  return res.json();
}

export async function askQuestion(question, mode = "basic") {
  const form = new FormData();
  form.append("question", question);
  form.append("mode", mode);
  const res = await fetch(ENDPOINTS.ASK, { method: "POST", body: form });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function askStream(question, mode = "basic", { signal } = {}) {
  const res = await fetch(ENDPOINTS.ASK_STREAM, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, mode }),
    signal,
  });
  if (!res.ok) throw new Error(await res.text());
  return res;
}

export async function fetchSource(docId) {
  if (!docId) throw new Error("docId required");
  const res = await fetch(ENDPOINTS.SOURCE(docId));
  if (res.status === 404) throw new Error("Source not found");
  if (!res.ok) throw new Error("Failed to fetch source");
  return res.json(); // { doc_id, text }
}

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

function defaultBackoff(attempt, base = 300, cap = 5000) {
  const exp = Math.min(cap, Math.round(base * Math.pow(1.8, attempt)));
  const jitter = (Math.random() * 0.4 - 0.2) * exp;
  return Math.max(50, Math.round(exp + jitter));
}

export async function pollUploadStatus(
  jobId,
  {
    onUpdate = () => {},
    maxAttempts = 20,
    allow404Retries = 6,
    stopWhen = (job) => job && ["completed", "error", "canceled"].includes(job.status),
  } = {}
) {
  let attempt = 0, notFound = 0, last = null;
  while (attempt < maxAttempts) {
    try {
      const job = await fetchUploadStatusRaw(jobId);
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
