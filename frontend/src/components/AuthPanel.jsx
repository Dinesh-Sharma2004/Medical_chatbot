import React, { useEffect, useRef, useState } from "react";
import { Eye, EyeOff, LogIn, LogOut, Mail, ShieldCheck, UserPlus } from "lucide-react";
import { getAuthConfig, loginUser, loginWithGoogle, registerUser } from "../api";
import { pushToast } from "./ToastContainer";

const GOOGLE_SCRIPT = "https://accounts.google.com/gsi/client";

function loadGoogleScript() {
  if (window.google?.accounts?.id) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${GOOGLE_SCRIPT}"]`);
    if (existing) {
      existing.addEventListener("load", resolve, { once: true });
      existing.addEventListener("error", reject, { once: true });
      return;
    }
    const script = document.createElement("script");
    script.src = GOOGLE_SCRIPT;
    script.async = true;
    script.defer = true;
    script.onload = resolve;
    script.onerror = reject;
    document.head.appendChild(script);
  });
}

export default function AuthPanel({ user, token, onAuth, onLogout, overlay = false }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [busy, setBusy] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [googleClientId, setGoogleClientId] = useState("");
  const googleRef = useRef(null);

  useEffect(() => {
    getAuthConfig()
      .then((cfg) => setGoogleClientId(cfg.google_client_id || ""))
      .catch(() => setGoogleClientId(""));
  }, []);

  useEffect(() => {
    if (!googleClientId || !googleRef.current || token) return;
    let mounted = true;
    loadGoogleScript()
      .then(() => {
        if (!mounted || !window.google?.accounts?.id) return;
        window.google.accounts.id.initialize({
          client_id: googleClientId,
          callback: async ({ credential }) => {
            try {
              const session = await loginWithGoogle(credential);
              onAuth(session);
              pushToast({ type: "success", title: "Signed in", msg: "Google authentication connected" });
            } catch (err) {
              pushToast({ type: "error", title: "Google sign-in failed", msg: err.message });
            }
          },
        });
        googleRef.current.innerHTML = "";
        window.google.accounts.id.renderButton(googleRef.current, {
          theme: "outline",
          size: "large",
          width: 280,
          text: "continue_with",
        });
      })
      .catch(() => {});
    return () => {
      mounted = false;
    };
  }, [googleClientId, onAuth, token]);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    try {
      const session =
        mode === "register"
          ? await registerUser(form)
          : await loginUser({ email: form.email, password: form.password });
      onAuth(session);
      pushToast({ type: "success", title: "Signed in", msg: "Chat history will sync to your account" });
    } catch (err) {
      pushToast({ type: "error", title: "Authentication failed", msg: err.message });
    } finally {
      setBusy(false);
    }
  }

  if (user) {
    return (
      <div className="rounded-lg border border-emerald-200 bg-emerald-50/80 p-3 text-sm dark:border-emerald-700/40 dark:bg-emerald-950/30">
        <div className="flex items-center gap-2 font-semibold text-emerald-800 dark:text-emerald-200">
          <ShieldCheck className="h-4 w-4" />
          {user.name || user.email}
        </div>
        <div className="mt-1 text-xs text-emerald-700 dark:text-emerald-300">
          Account verified. History sync is enabled.
        </div>
        <button
          type="button"
          onClick={onLogout}
          className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-md border border-emerald-300 px-3 py-2 text-xs font-semibold text-emerald-800 transition hover:bg-emerald-100 dark:border-emerald-700 dark:text-emerald-200 dark:hover:bg-emerald-900/40"
        >
          <LogOut className="h-4 w-4" />
          Sign out
        </button>
      </div>
    );
  }

  return (
    <div className={`rounded-lg border border-gray-200 bg-white/90 p-3 shadow-sm dark:border-slate-700 dark:bg-slate-900/85 ${overlay ? "w-full max-w-md p-6 shadow-2xl" : ""}`}>
      {overlay && (
        <div className="mb-4">
          <div className="text-xl font-bold text-gray-900 dark:text-white">Sign in to unlock MediBot</div>
          <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">
            Chat and upload stay protected until you register or sign in.
          </p>
        </div>
      )}
      <div className="mb-3 flex rounded-md bg-gray-100 p-1 text-xs font-semibold dark:bg-slate-800">
        <button
          type="button"
          onClick={() => setMode("login")}
          className={`flex-1 rounded px-2 py-1.5 ${mode === "login" ? "bg-white text-cyan-700 shadow-sm dark:bg-slate-700 dark:text-cyan-200" : "text-gray-600 dark:text-gray-300"}`}
        >
          Login
        </button>
        <button
          type="button"
          onClick={() => setMode("register")}
          className={`flex-1 rounded px-2 py-1.5 ${mode === "register" ? "bg-white text-cyan-700 shadow-sm dark:bg-slate-700 dark:text-cyan-200" : "text-gray-600 dark:text-gray-300"}`}
        >
          Register
        </button>
      </div>

      <form className="space-y-2" onSubmit={submit}>
        {mode === "register" && (
          <input
            value={form.name}
            onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
            placeholder="Name"
            className="w-full rounded-md border border-gray-200 bg-white px-3 py-2 text-sm outline-none focus:border-cyan-500 dark:border-slate-700 dark:bg-slate-950"
          />
        )}
        <input
          value={form.email}
          onChange={(e) => setForm((p) => ({ ...p, email: e.target.value }))}
          placeholder="Email"
          type="email"
          className="w-full rounded-md border border-gray-200 bg-white px-3 py-2 text-sm outline-none focus:border-cyan-500 dark:border-slate-700 dark:bg-slate-950"
          required
        />
        <div className="relative">
          <input
            value={form.password}
            onChange={(e) => setForm((p) => ({ ...p, password: e.target.value }))}
            placeholder="Password"
            type={showPassword ? "text" : "password"}
            minLength={6}
            className="w-full rounded-md border border-gray-200 bg-white px-3 py-2 pr-10 text-sm outline-none focus:border-cyan-500 dark:border-slate-700 dark:bg-slate-950"
            required
          />
          <button
            type="button"
            onClick={() => setShowPassword((value) => !value)}
            className="absolute inset-y-0 right-0 inline-flex items-center justify-center px-3 text-gray-500 transition hover:text-cyan-600 dark:text-gray-400 dark:hover:text-cyan-300"
            aria-label={showPassword ? "Hide password" : "Show password"}
            title={showPassword ? "Hide password" : "Show password"}
          >
            {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        </div>
        <button
          disabled={busy}
          className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-cyan-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-cyan-700 disabled:opacity-60"
        >
          {mode === "register" ? <UserPlus className="h-4 w-4" /> : <LogIn className="h-4 w-4" />}
          {busy ? "Please wait..." : mode === "register" ? "Create account" : "Sign in"}
        </button>
      </form>

      {googleClientId && (
        <div className="mt-3 border-t border-gray-200 pt-3 dark:border-slate-700">
          <div ref={googleRef} className="min-h-10" />
        </div>
      )}
      {!googleClientId && (
        <div className="mt-3 flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
          <Mail className="h-3.5 w-3.5" />
          Add GOOGLE_CLIENT_ID to enable Google.
        </div>
      )}
    </div>
  );
}
