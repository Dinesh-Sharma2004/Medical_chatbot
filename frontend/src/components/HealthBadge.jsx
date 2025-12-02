// HealthBadge.jsx
import React, { useEffect, useState } from "react";
import { CheckCircle, XCircle, Clock, Database } from "lucide-react";
import { health } from "../api";  // ⬅ updated import

export default function HealthBadge() {
  const [backendOk, setBackendOk] = useState(null);
  const [vectorReady, setVectorReady] = useState(null);

  useEffect(() => {
    let mounted = true;

    const checkHealth = () => {
      health()
        .then((d) => {
          if (!mounted) return;
          setBackendOk(d?.status === "ok");
          setVectorReady(Boolean(d?.vector_ready));
        })
        .catch(() => {
          if (!mounted) return;
          setBackendOk(false);
          setVectorReady(false);
        });
    };

    checkHealth();
    const interval = setInterval(checkHealth, 30000);

    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  let content = null;
  let bg = "";
  let glow = "";

  if (backendOk === null) {
    bg =
      "bg-gray-100 dark:bg-slate-800 text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-gray-700";
    glow = "bg-gray-500";
    content = (
      <>
        <Clock className="w-4 h-4 animate-spin" />
        <span>Checking backend…</span>
      </>
    );
  } else if (!backendOk) {
    bg =
      "bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 border border-red-200 dark:border-red-500/30";
    glow = "bg-red-500";
    content = (
      <>
        <XCircle className="w-4 h-4 animate-pulse" />
        <span>Backend Offline</span>
      </>
    );
  } else if (backendOk && !vectorReady) {
    bg =
      "bg-yellow-50 dark:bg-yellow-900/20 text-yellow-700 dark:text-yellow-400 border border-yellow-200 dark:border-yellow-500/30";
    glow = "bg-yellow-500";
    content = (
      <>
        <Database className="w-4 h-4 animate-pulse" />
        <span>Index Not Ready</span>
      </>
    );
  } else {
    bg =
      "bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400 border border-green-200 dark:border-green-500/30";
    glow = "bg-green-500";
    content = (
      <>
        <div className="relative">
          <CheckCircle className="w-4 h-4" />
          <div className="absolute inset-0 animate-ping">
            <CheckCircle className="w-4 h-4 opacity-75" />
          </div>
        </div>
        <span>Backend & Index Ready</span>
      </>
    );
  }

  return (
    <div
      className={`group relative flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium
                   transition-all duration-300 hover:scale-105 ${bg}`}
    >
      {content}
      <div
        className={`absolute -inset-1 rounded-lg blur-sm transition-opacity duration-300 opacity-0 group-hover:opacity-50 -z-10 ${glow}`}
      ></div>
    </div>
  );
}
