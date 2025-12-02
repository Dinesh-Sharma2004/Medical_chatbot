// frontend/src/hooks/useUploadJob.js
import { useEffect, useRef, useState } from "react";
import {
  startUpload,
  cancelUpload as apiCancelUpload,
  deleteUpload as apiDeleteUpload,
  pollUploadStatus,
  resumeLastUploadPolling,
} from "../api";

/**
 * useUploadJob
 *
 * - start(file, { onStarted }) -> starts upload, returns server response (job_id etc)
 * - cancel() -> requests server cancel + stops local polling
 * - clear() -> clears hook state (does not delete server job unless deleteSelected is called)
 *
 * Exposes:
 * { jobId, status, progress, detail, filename, sizeText, uploading, error, start, cancel, clear }
 */
export default function useUploadJob({ pollInterval = 800 } = {}) {
  const [jobId, setJobId] = useState(null);
  const [status, setStatus] = useState(null);
  const [progress, setProgress] = useState(null);
  const [detail, setDetail] = useState(null);
  const [filename, setFilename] = useState(null);
  const [sizeText, setSizeText] = useState("-");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);

  // internal refs so cancel() can stop polling
  const pollingCancelRef = useRef({ cancelled: false });
  const currentJobRef = useRef(null);

  // Helper: update state from job object returned by backend
  function _applyJob(job) {
    currentJobRef.current = job || null;
    if (!job) {
      setStatus((s) => (s === null ? null : s));
      return;
    }
    setJobId(job.job_id || job.jobId || job.job_id || job.jobId || job.jobId); // fallback keys
    setStatus(job.status ?? job.state ?? null);
    setProgress(job.progress ?? null);
    setDetail(job.detail ?? job.message ?? null);
    setFilename(job.filename ?? null);
    if (job.size_bytes != null) {
      const b = parseInt(job.size_bytes, 10);
      setSizeText(_fmtBytes(b));
    } else if (job.size_mb != null) {
      setSizeText(`${job.size_mb} MB`);
    }
    if (job.error) setError(job.error);
  }

  function _fmtBytes(bytes) {
    if (bytes == null) return "-";
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB", "TB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
  }

  // Start upload; options: { onStarted(job), onUpdate(job) }
  async function start(file, { onStarted = () => {}, onUpdate = () => {} } = {}) {
    setError(null);
    setUploading(true);

    try {
      const res = await startUpload(file);
      // server responded with job object (job_id etc)
      const jid = res.job_id || res.jobId || res.id;
      setJobId(jid);
      setFilename(res.filename ?? file.name);
      if (res.size_bytes != null) setSizeText(_fmtBytes(res.size_bytes));
      setStatus(res.status ?? "uploading");
      setProgress(res.progress ?? 0);
      setDetail(res.detail ?? "Queued");

      try {
        onStarted(res);
      } catch (_) {}

      // reset previous cancel
      pollingCancelRef.current.cancelled = false;

      // start polling with pollUploadStatus helper
      // pollUploadStatus will call onUpdate per poll; we forward to local state
      const job = await pollUploadStatus(jid, {
        onUpdate: (jobObj) => {
          _applyJob(jobObj);
          try {
            onUpdate(jobObj);
          } catch (_) {}
        },
        // give enough attempts, you can tune these
        maxAttempts: 60,
        allow404Retries: 6,
        stopWhen: (jobObj) =>
          jobObj && Array.isArray(["completed", "error", "canceled"]) && ["completed", "error", "canceled"].includes(jobObj.status),
      });

      // Apply final state
      _applyJob(job);
      setUploading(false);
      return job;
    } catch (err) {
      console.error("startUpload failed", err);
      setError(err.message || String(err));
      setUploading(false);
      throw err;
    }
  }

  // Cancel the job: request server to cancel + stop polling locally
  async function cancel() {
    try {
      pollingCancelRef.current.cancelled = true; // signal to stop any local flow
      const jid = jobId || (currentJobRef.current && currentJobRef.current.job_id);
      if (!jid) {
        // nothing to cancel
        setStatus("canceled");
        setUploading(false);
        return null;
      }
      try {
        const res = await apiCancelUpload(jid);
        // update local state based on server response
        setStatus(res.status || "cancel_requested");
        setDetail(res.detail || "Cancel requested");
      } catch (err) {
        // network or server error; still mark canceled locally
        console.warn("apiCancelUpload failed", err);
        setError(err.message || String(err));
      } finally {
        setUploading(false);
      }
    } catch (err) {
      console.warn("cancel() error", err);
      setError(err.message || String(err));
    }
  }

  // Clear hook state and optionally delete server-side saved file/metadata
  function clear(opts = { deleteServer: false }) {
    if (opts.deleteServer && jobId) {
      // fire-and-forget server delete
      apiDeleteUpload(jobId).catch((e) => console.warn("deleteUpload failed", e));
      try {
        localStorage.removeItem("last_upload_job_id");
      } catch (_) {}
    }
    pollingCancelRef.current.cancelled = true;
    setJobId(null);
    setStatus(null);
    setProgress(null);
    setDetail(null);
    setFilename(null);
    setSizeText("-");
    setUploading(false);
    setError(null);
    currentJobRef.current = null;
  }

  // On mount: try to resume any last upload found in localStorage
  useEffect(() => {
    let mounted = true;
    const tryResume = async () => {
      try {
        const resumed = await resumeLastUploadPolling({
          onUpdate: (jobObj) => {
            if (!mounted) return;
            _applyJob(jobObj);
          },
        });
        if (!mounted) return;
        if (resumed) {
          _applyJob(resumed);
          setUploading(false);
        }
      } catch (err) {
        // ignore resume errors
        console.warn("resumeLastUploadPolling failed", err);
      }
    };
    tryResume();
    return () => {
      mounted = false;
      pollingCancelRef.current.cancelled = true;
    };
  }, []);

  return {
    // state
    jobId,
    status,
    progress,
    detail,
    filename,
    sizeText,
    uploading,
    error,

    // actions
    start,
    cancel,
    clear,
  };
}
