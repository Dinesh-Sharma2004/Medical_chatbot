import React, { useState, useEffect } from "react";

let toastId = 0;

// Exported function exactly how UploadPage needs it
export function pushToast({ title, msg, type = "info" }) {
  window.dispatchEvent(
    new CustomEvent("medibot_toast", {
      detail: {
        id: ++toastId,
        title,
        msg,
        type,
      },
    })
  );
}

export default function ToastContainer() {
  const [toasts, setToasts] = useState([]);

  useEffect(() => {
    const handler = (e) => {
      const toast = e.detail;
      setToasts((prev) => [...prev, toast]);

      // Auto-remove after 4s
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== toast.id));
      }, 4000);
    };

    window.addEventListener("medibot_toast", handler);
    return () => window.removeEventListener("medibot_toast", handler);
  }, []);

  const colors = {
    info: "bg-blue-600",
    success: "bg-green-600",
    error: "bg-red-600",
    warning: "bg-yellow-600",
  };

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-3 pointer-events-none">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`pointer-events-auto w-72 px-4 py-3 rounded-xl shadow-lg text-white ${colors[t.type]}
                     animate-slide-up`}
        >
          <div className="font-semibold">{t.title}</div>
          <div className="text-sm opacity-90">{t.msg}</div>
        </div>
      ))}
    </div>
  );
}
