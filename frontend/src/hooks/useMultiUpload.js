import { useState, useEffect, useRef } from "react";
import {
  startUpload,
  startBatchUpload,
  getUploadStatus,
  cancelUpload,
  deleteUpload,
  ENDPOINTS,
} from "../api";

const STORAGE_KEY = "medibot_jobs_v1";
const RESUME_KEY = "last_upload_job_id";

function derivePhase(job = {}) {
  const status = String(job.status || "").toLowerCase();
  const detail = String(job.detail || "").toLowerCase();
  const progress = Number(job.progress || 0);

  if (status === "completed") {
    return {
      phase: "ready",
      phaseLabel: "Ready to chat",
      summary: job.detail || "Document indexing finished.",
    };
  }

  if (status === "error" || status === "failed") {
    return {
      phase: "failed",
      phaseLabel: "Indexing failed",
      summary: job.detail || job.error || "The upload finished, but indexing did not complete.",
    };
  }

  if (status === "canceled") {
    return {
      phase: "canceled",
      phaseLabel: "Canceled",
      summary: job.detail || "Upload or indexing was canceled.",
    };
  }

  if (detail.includes("queued")) {
    return {
      phase: "queued",
      phaseLabel: "Queued",
      summary: job.detail || "The file is waiting for the ingestion worker.",
    };
  }

  if (
    detail.includes("extract") ||
    detail.includes("index") ||
    detail.includes("worker") ||
    detail.includes("vector") ||
    progress > 0
  ) {
    return {
      phase: "indexing",
      phaseLabel: "Indexing",
      summary: job.detail || "The PDF is being processed into the vector database.",
    };
  }

  return {
    phase: "uploaded",
    phaseLabel: "Uploaded",
    summary: job.detail || "The file upload finished and indexing is about to start.",
  };
}

function normalizeJob(job = {}) {
  return {
    ...job,
    ...derivePhase(job),
  };
}

export function useMultiUpload(token) {
  const [jobs, setJobs] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {};
    } catch {
      return {};
    }
  });

  const jobsRef = useRef(jobs);
  useEffect(() => {
    jobsRef.current = jobs;
  }, [jobs]);

  const pollRef = useRef(null);
  const pollStateRef = useRef({
    busy: false,
    networkFailCount: 0,
    paused: false,
  });

  // persist safely to localStorage
  const persist = (updater) => {
    setJobs((prev) => {
      const next = typeof updater === "function" ? updater(prev) : updater;
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      } catch (e) {
        console.warn("Failed to persist jobs to localStorage", e);
      }
      jobsRef.current = next;
      return next;
    });
  };

  // === Upload Multiple Files ===
  const uploadFiles = async (fileList) => {
    const arr = Array.from(fileList);
    if (arr.length === 0) return;
    if (arr.length === 1) {
      await addSingleFile(arr[0]);
      return;
    }
    await addBatch(arr);
  };

  // === Add Single File ===
  const addSingleFile = async (file) => {
    const res = await startUpload(file, { token });
    if (!res || !res.ok) {
      console.warn("startUpload did not return ok:", res);
      return;
    }

    const jobId = res.job_id;
    try {
      if (jobId) localStorage.setItem(RESUME_KEY, jobId);
    } catch (_) {}

    persist((prev) => ({
      ...prev,
      [jobId]: normalizeJob({
        jobId,
        fileName: res.filename || file.name,
        size_bytes: res.size_bytes || file.size || 0, // ✅ always set from File
        progress: res.progress || 0,
        detail: res.detail || "Queued for indexing",
        status: res.status || "processing",
        eta: null,
        duration: null,
      }),
    }));

    console.info("Started upload", jobId, res.filename);
    startPolling();
  };

  const addBatch = async (files) => {
    const res = await startBatchUpload(files, { token });
    if (!res || !res.ok) {
      console.warn("startBatchUpload did not return ok:", res);
      return;
    }

    const jobId = res.job_id;
    try {
      if (jobId) localStorage.setItem(RESUME_KEY, jobId);
    } catch (_) {}

    persist((prev) => ({
      ...prev,
      [jobId]: normalizeJob({
        jobId,
        fileName: res.filename || `${files.length} PDFs`,
        fileNames: res.filenames || files.map((file) => file.name),
        size_bytes:
          res.size_bytes ||
          files.reduce((sum, file) => sum + (file.size || 0), 0),
        progress: res.progress || 0,
        detail: res.detail || "Queued batch for indexing",
        status: res.status || "processing",
        eta: null,
        duration: null,
      }),
    }));

    console.info("Started batch upload", jobId, res.filenames);
    startPolling();
  };

  // === Polling ===
  const NETWORK_RETRY_BASE = 1000;
  const NETWORK_RETRY_MAX = 30_000;

  const pollAll = async () => {
    const pollState = pollStateRef.current;
    if (pollState.busy || pollState.paused) return;

    const entries = Object.entries(jobsRef.current || {});
    if (entries.length === 0) return;

    pollState.busy = true;
    const next = { ...(jobsRef.current || {}) };
    let sawNetworkError = false;

    for (const [jobId, job] of entries) {
      try {
        const status = await getUploadStatus(jobId, token);
        next[jobId] = normalizeJob({
          ...job,
          ...status,
          fileName: status.filename || job.fileName,
          size_bytes:
            status.size_bytes ??
            job.size_bytes ??
            0, // ✅ ensure never undefined
        });

        const st = (status.status || "").toLowerCase();
        if (["completed", "error", "canceled"].includes(st)) {
          try {
            const stored = localStorage.getItem(RESUME_KEY);
            if (stored === jobId) localStorage.removeItem(RESUME_KEY);
          } catch (_) {}
        }
      } catch (err) {
        if (err && err.code === 404) {
          delete next[jobId];
          try {
            const stored = localStorage.getItem(RESUME_KEY);
            if (stored === jobId) localStorage.removeItem(RESUME_KEY);
          } catch (_) {}
          console.info("Removed missing job (server 404):", jobId);
          continue;
        }

        const isNetwork = err instanceof TypeError || !err.code;
        if (isNetwork) {
          sawNetworkError = true;
          console.warn("Network error while polling job", jobId, err);
        } else {
          console.warn("Poll HTTP error for job", jobId, err);
        }
      }
    }

    persist(next);
    pollState.busy = false;

    if (sawNetworkError) {
      pollState.networkFailCount = (pollState.networkFailCount || 0) + 1;
      const backoff = Math.min(
        NETWORK_RETRY_BASE * Math.pow(1.8, pollState.networkFailCount - 1),
        NETWORK_RETRY_MAX
      );
      console.warn(
        `Pausing job polling due to network error. Will retry in ${Math.round(backoff)}ms`
      );
      pollState.paused = true;
      stopPolling();

      const probe = async () => {
        try {
          const h = await fetch(ENDPOINTS.HEALTH, { cache: "no-store" });
          if (h.ok) {
            console.info("Backend reachable again; resuming job polling");
            pollState.networkFailCount = 0;
            pollState.paused = false;
            startPolling();
            setTimeout(() => pollAll().catch(() => {}), 100);
            return;
          }
        } catch (e) {}
        pollState.networkFailCount = Math.min(
          (pollState.networkFailCount || 0) + 1,
          10
        );
        const nextBackoff = Math.min(
          NETWORK_RETRY_BASE *
            Math.pow(1.8, pollState.networkFailCount - 1),
          NETWORK_RETRY_MAX
        );
        setTimeout(probe, nextBackoff);
      };

      setTimeout(probe, backoff);
    } else {
      pollState.networkFailCount = 0;
    }
  };

  const startPolling = () => {
    if (pollRef.current) return;
    pollRef.current = setInterval(() => {
      pollAll().catch((e) => console.warn("pollAll error:", e));
    }, 900);
  };

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  // === Cancel functions ===
  const cancelOne = async (jobId) => {
    try {
        await cancelUpload(jobId, token);
        await deleteUpload(jobId, token);
    } catch (err) {
      console.warn("cancel/delete failed", err);
    }

    persist((prev) => {
      const copy = { ...prev };
      delete copy[jobId];
      return copy;
    });

    try {
      const stored = localStorage.getItem(RESUME_KEY);
      if (stored === jobId) localStorage.removeItem(RESUME_KEY);
    } catch (_) {}
  };

  const cancelAll = async () => {
    const ids = Object.keys(jobsRef.current || {});
    for (const id of ids) {
      try {
        await cancelUpload(id, token);
        await deleteUpload(id, token);
      } catch (_) {}
    }
    persist({});
    try {
      localStorage.removeItem(RESUME_KEY);
    } catch (_) {}
  };

  // === Sort jobs by status and size for UI ===
  const sortedJobs = Object.values(jobs).sort((a, b) => {
    const order = {
      processing: 1,
      uploading: 1,
      queued: 2,
      completed: 3,
      canceled: 4,
      error: 5,
    };
    const sa = order[a.status] || 99;
    const sb = order[b.status] || 99;
    if (sa !== sb) return sa - sb;
    return (b.size_bytes || 0) - (a.size_bytes || 0);
  });

  useEffect(() => {
    const pending = Object.values(jobsRef.current || {}).some((j) =>
      (j.status || "").match(/processing|uploading|queued|in_progress/i)
    );
    if (pending) startPolling();
    return () => stopPolling();
  }, []);

  return {
    jobs: sortedJobs, // ✅ sorted
    uploadFiles,
    cancelOne,
    cancelAll,
  };
}

export default useMultiUpload;
