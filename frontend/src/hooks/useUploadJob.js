// frontend/src/hooks/useUploadJob.js
import { useEffect, useRef, useState } from "react";
import {
  startUpload,
  cancelUpload as apiCancelUpload,
  deleteUpload as apiDeleteUpload,
  pollUploadStatus,
  resumeLastUploadPolling,
} from "../api";

const STORAGE_KEY = "medibot_jobs_v1";
const RESUME_KEY = "last_upload_job_id";

export default function useUploadJob({ pollInterval = 800 } = {}) {
  const [jobId, setJobId] = useState(null);
  const [status, setStatus] = useState(null);
  const [progress, setProgress] = useState(null);
  const [detail, setDetail] = useState(null);
  const [filename, setFilename] = useState(null);
  const [sizeText, setSizeText] = useState("-");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);

  const pollingCancelRef = useRef({ cancelled: false });
  const currentJobRef = useRef(null);

  function _applyJob(job) {
    currentJobRef.current = job || null;
    if (!job) {
      return;
    }

    // Normalize job id keys
    const jid = job.job_id ?? job.jobId ?? job.id ?? job.upload_id ?? null;
    if (jid) setJobId(jid);

    const rawStatus = (job.status ?? job.state ?? "").toString();
    const s = rawStatus ? rawStatus.toLowerCase() : null;
    setStatus(s);
    setProgress(typeof job.progress === "number" ? job.progress : (job.progress ?? progress));
    setDetail(job.detail ?? job.message ?? detail);
    setFilename(job.filename ?? filename);

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

  // Start upload
  async function start(file, { onStarted = () => {}, onUpdate = () => {} } = {}) {
    setError(null);
    setUploading(true);

    try {
      const res = await startUpload(file);
      const jid = res.job_id ?? res.jobId ?? res.id ?? res.upload_id ?? null;

      if (jid) {
        // persist resume key immediately so other hooks won't resume an older id
        try {
          localStorage.setItem(RESUME_KEY, jid);
        } catch (_) {}
      }

      setJobId(jid);
      setFilename(res.filename ?? file.name);
      if (res.size_bytes != null) setSizeText(_fmtBytes(res.size_bytes));
      setStatus((res.status ?? "uploading").toString().toLowerCase());
      setProgress(res.progress ?? 0);
      setDetail(res.detail ?? "Queued");

      try { onStarted(res); } catch (_) {}

      pollingCancelRef.current.cancelled = false;

      // pollUploadStatus should return final job or throw
      const finalJob = await pollUploadStatus(jid, {
        onUpdate: (jobObj) => {
          _applyJob(jobObj);
          try { onUpdate(jobObj); } catch (_) {}
        },
        maxAttempts: 60,
        allow404Retries: 6,
        stopWhen: (jobObj) => {
          const st = (jobObj?.status ?? jobObj?.state ?? "").toString().toLowerCase();
          return ["completed", "error", "canceled"].includes(st);
        },
      });

      // Apply final state
      _applyJob(finalJob || currentJobRef.current);

      // terminal state reached: clear resume key if it matches
      try {
        const stored = localStorage.getItem(RESUME_KEY);
        if (stored && stored === (jid || stored)) {
          localStorage.removeItem(RESUME_KEY);
        }
      } catch (_) {}

      setUploading(false);
      return finalJob;
    } catch (err) {
      console.error("startUpload failed", err);
      setError(err.message || String(err));
      setUploading(false);
      throw err;
    }
  }

  // Cancel
  async function cancel() {
    try {
      pollingCancelRef.current.cancelled = true;
      const jid = jobId || (currentJobRef.current && (currentJobRef.current.job_id ?? currentJobRef.current.jobId));
      if (!jid) {
        setStatus("canceled");
        setUploading(false);
        return null;
      }
      try {
        const res = await apiCancelUpload(jid);
        setStatus((res.status ?? "cancel_requested").toString().toLowerCase());
        setDetail(res.detail ?? "Cancel requested");
      } catch (err) {
        console.warn("apiCancelUpload failed", err);
        setError(err.message || String(err));
      } finally {
        // clear resume key if it was pointing to this job
        try {
          const stored = localStorage.getItem(RESUME_KEY);
          if (stored === jid) localStorage.removeItem(RESUME_KEY);
        } catch (_) {}
        setUploading(false);
      }
    } catch (err) {
      console.warn("cancel() error", err);
      setError(err.message || String(err));
    }
  }

  // Clear hook state
  function clear(opts = { deleteServer: false }) {
    if (opts.deleteServer && jobId) {
      apiDeleteUpload(jobId).catch((e) => console.warn("deleteUpload failed", e));
      try { localStorage.removeItem(RESUME_KEY); } catch (_) {}
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

  // On mount: try resume, but only if multi-upload store isn't active
  useEffect(() => {
    let mounted = true;
    const tryResume = async () => {
      try {
        // if multi-upload state exists, don't auto-resume single-job flow
        const multi = localStorage.getItem(STORAGE_KEY);
        if (multi) {
          console.info("Multi-upload state present; skipping single-job resume.");
          return;
        }

        const resumed = await resumeLastUploadPolling({
          onUpdate: (jobObj) => {
            if (!mounted) return;
            _applyJob(jobObj);
          },
        });
        if (!mounted) return;
        if (resumed) {
          _applyJob(resumed);
          // remove resume key after restoring state so we don't resume again incorrectly
          try { localStorage.removeItem(RESUME_KEY); } catch (_) {}
          setUploading(false);
        }
      } catch (err) {
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
    jobId,
    status,
    progress,
    detail,
    filename,
    sizeText,
    uploading,
    error,
    start,
    cancel,
    clear,
  };
}
