import React, { useState } from "react";
import { useMultiUpload } from "../hooks/useMultiUpload";
import {
  UploadCloud,
  FileText,
  XCircle,
  CheckCircle,
} from "lucide-react";

export default function UploadPage() {
  const [selected, setSelected] = useState([]);
  const { jobs, uploadFiles, cancelOne, cancelAll } = useMultiUpload();

  const handleUpload = () => {
    if (!selected.length) return;
    uploadFiles(selected);
  };

  // Safe size formatter
  const formatBytes = (b) => {
    if (!b || isNaN(b)) return "0 MB";
    return `${(b / 1024 / 1024).toFixed(2)} MB`;
  };

  // Filter out failed/error jobs
  const visibleJobs = Object.values(jobs).filter(
    (job) => job.status !== "error" && job.status !== "failed"
  );

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
            onChange={(e) => setSelected(e.target.files)}
            className="w-full px-4 py-3 rounded-xl bg-gray-50 dark:bg-slate-800 border border-gray-300 
                       dark:border-gray-600 text-gray-900 dark:text-gray-200"
          />

          <button
            onClick={handleUpload}
            disabled={!selected.length}
            className="w-full py-3 rounded-xl text-lg font-semibold text-white 
                       bg-gradient-to-r from-cyan-600 to-blue-600 hover:scale-[1.04]
                       active:scale-95 shadow-xl transition-all"
          >
            Upload {selected.length} files
          </button>

          {Object.keys(jobs).length > 1 && (
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

                {/* Progress bar */}
                <div className="w-full bg-gray-200 dark:bg-gray-700 h-3 rounded-xl overflow-hidden">
                  <div
                    className="bg-gradient-to-r from-cyan-500 to-blue-600 h-full transition-all"
                    style={{ width: `${job.progress || 0}%` }}
                  />
                </div>

                {/* Detail */}
                <div className="text-gray-700 dark:text-gray-300">
                  {job.detail}
                </div>

                {/* Status row */}
                <div className="flex items-center gap-4 text-sm text-gray-600 dark:text-gray-400">
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
            ))
          )}
        </div>
      </div>
    </div>
  );
}
