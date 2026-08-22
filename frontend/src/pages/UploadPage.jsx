import React, { useState } from "react";
import { useMultiUpload } from "../hooks/useMultiUpload";
import {
  UploadCloud,
  FileText,
  XCircle,
  CheckCircle,
  AlertCircle,
  Clock3,
  LoaderCircle,
} from "lucide-react";
import { pushToast } from "../components/ToastContainer";

const PHASE_STYLES = {
  uploaded: {
    label: "Uploaded",
    text: "text-sky-700 dark:text-sky-300",
    bg: "bg-sky-50 dark:bg-sky-950/30",
    border: "border-sky-200 dark:border-sky-800/40",
    icon: FileText,
  },
  queued: {
    label: "Queued",
    text: "text-amber-700 dark:text-amber-300",
    bg: "bg-amber-50 dark:bg-amber-950/30",
    border: "border-amber-200 dark:border-amber-800/40",
    icon: Clock3,
  },
  indexing: {
    label: "Indexing",
    text: "text-cyan-700 dark:text-cyan-300",
    bg: "bg-cyan-50 dark:bg-cyan-950/30",
    border: "border-cyan-200 dark:border-cyan-800/40",
    icon: LoaderCircle,
  },
  ready: {
    label: "Ready to chat",
    text: "text-emerald-700 dark:text-emerald-300",
    bg: "bg-emerald-50 dark:bg-emerald-950/30",
    border: "border-emerald-200 dark:border-emerald-800/40",
    icon: CheckCircle,
  },
  failed: {
    label: "Indexing failed",
    text: "text-red-700 dark:text-red-300",
    bg: "bg-red-50 dark:bg-red-950/30",
    border: "border-red-200 dark:border-red-800/40",
    icon: AlertCircle,
  },
  canceled: {
    label: "Canceled",
    text: "text-slate-700 dark:text-slate-300",
    bg: "bg-slate-100 dark:bg-slate-800/60",
    border: "border-slate-200 dark:border-slate-700",
    icon: XCircle,
  },
};

export default function UploadPage({ token }) {
  const [selected, setSelected] = useState([]);
  const { jobs, uploadFiles, cancelOne, cancelAll } = useMultiUpload(token);

  const handleUpload = async () => {
    if (!selected.length) return;
    try {
      await uploadFiles(selected);
      setSelected([]);
    } catch (err) {
      pushToast({
        type: "error",
        title: "Upload failed",
        msg: err?.message || "Could not start upload",
      });
    }
  };

  // Safe size formatter
  const formatBytes = (b) => {
    if (!b || isNaN(b)) return "0 MB";
    return `${(b / 1024 / 1024).toFixed(2)} MB`;
  };

  const visibleJobs = Array.isArray(jobs) ? jobs : Object.values(jobs || {});

  return (
    <div className="max-w-4xl mx-auto pt-10 px-4">
      <div className="bg-white dark:bg-slate-900 shadow-2xl rounded-3xl border-2 border-gray-200 
                      dark:border-cyan-500/20 p-10 space-y-10">

        {/* Header */}
        <div className="flex items-center gap-4">
          <div className="p-3 bg-gradient-to-br from-cyan-500 to-blue-600 rounded-2xl shadow-xl">
            <UploadCloud className="text-white w-8 h-8" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
              Upload Multiple PDFs
            </h1>
            <p className="text-gray-600 dark:text-gray-400">
              All PDF files will be processed into the vector database.
            </p>
          </div>
        </div>

        {/* File Selector */}
        <div className="space-y-4">
          <input
            type="file"
            accept="application/pdf"
            multiple
            disabled={!token}
            onChange={(e) => setSelected(Array.from(e.target.files || []))}
            className="w-full px-4 py-3 rounded-xl bg-gray-50 dark:bg-slate-800 border border-gray-300 
                       dark:border-gray-600 text-gray-900 dark:text-gray-200"
          />

          {!token && (
            <div className="text-sm text-amber-700 dark:text-amber-300">
              Sign in to upload and index PDFs.
            </div>
          )}

          <button
            onClick={handleUpload}
            disabled={!selected.length || !token}
            className="w-full py-3 rounded-xl text-lg font-semibold text-white 
                       bg-gradient-to-r from-cyan-600 to-blue-600 hover:scale-[1.04]
                       active:scale-95 shadow-xl transition-all disabled:cursor-not-allowed disabled:opacity-60"
          >
            Upload {selected.length} files
          </button>

          {visibleJobs.length > 1 && (
              <button
                onClick={cancelAll}
                className="w-full py-3 rounded-xl text-red-600 border border-red-300 
                         dark:border-red-800 hover:bg-red-50 dark:hover:bg-red-900/20"
            >
              Cancel All Uploads
            </button>
          )}
        </div>

        {/* Job List */}
        <div className="space-y-6">
          {visibleJobs.length === 0 ? (
            <p className="text-gray-500 dark:text-gray-400 text-center italic">
              No active uploads.
            </p>
          ) : (
            visibleJobs.map((job) => (
              (() => {
                const phaseStyle = PHASE_STYLES[job.phase] || PHASE_STYLES.uploaded;
                const PhaseIcon = phaseStyle.icon;

                return (
                  <div
                    key={job.jobId}
                    className="p-5 rounded-2xl bg-gradient-to-b from-gray-50 to-white dark:from-slate-800 dark:to-slate-900
                               border-2 border-cyan-200 dark:border-cyan-500/30 shadow-xl space-y-4"
                  >
                {/* File + size */}
                <div className="flex items-center gap-3">
                  <FileText className="text-cyan-600 dark:text-cyan-400" />
                  <span className="font-semibold dark:text-white">
                    {job.fileName}
                  </span>
                  <span className="text-sm text-gray-500 dark:text-gray-400">
                    ({formatBytes(job.size_bytes)})
                  </span>
                </div>

                <div className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold ${phaseStyle.text} ${phaseStyle.bg} ${phaseStyle.border}`}>
                  <PhaseIcon className={`w-3.5 h-3.5 ${job.phase === "indexing" ? "animate-spin" : ""}`} />
                  {job.phaseLabel || phaseStyle.label}
                </div>

                {/* Progress bar */}
                <div className="w-full bg-gray-200 dark:bg-gray-700 h-3 rounded-xl overflow-hidden">
                  <div
                    className="bg-gradient-to-r from-cyan-500 to-blue-600 h-full transition-all"
                    style={{ width: `${job.progress || 0}%` }}
                  />
                </div>

                {/* Detail */}
                <div
                  className={`text-sm ${
                    job.status === "error" || job.status === "failed"
                      ? "text-red-600 dark:text-red-400"
                      : "text-gray-700 dark:text-gray-300"
                  }`}
                >
                  {job.status === "error" || job.status === "failed" ? (
                    <div className="flex items-start gap-2">
                      <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                      <span>{job.detail || job.error || "Upload failed"}</span>
                    </div>
                  ) : (
                    job.detail
                  )}
                </div>

                {/* Status row */}
                <div className="flex items-center gap-4 text-sm text-gray-600 dark:text-gray-400">
                  <div>{job.summary}</div>
                  {job.status === "completed" && job.duration && (
                    <div className="flex items-center gap-1 text-green-600 dark:text-green-400">
                      <CheckCircle className="w-4 h-4" /> Done in{" "}
                      {job.duration}s
                    </div>
                  )}

                  {job.status === "canceled" && (
                    <div className="flex items-center gap-1 text-red-500">
                      <XCircle className="w-4 h-4" /> Canceled
                    </div>
                  )}

                  {(job.status === "error" || job.status === "failed") && (
                    <div className="flex items-center gap-1 text-red-600 dark:text-red-400">
                      <AlertCircle className="w-4 h-4" /> Failed
                    </div>
                  )}
                </div>

                {/* Cancel button */}
                {job.status === "processing" && (
                  <button
                    onClick={() => cancelOne(job.jobId)}
                    className="px-4 py-2 rounded-lg text-red-600 border border-red-300 
                               dark:border-red-800 dark:hover:bg-red-900/20 hover:bg-red-50"
                  >
                    Cancel
                  </button>
                )}
                  </div>
                );
              })()
            ))
          )}
        </div>
      </div>
    </div>
  );
}
