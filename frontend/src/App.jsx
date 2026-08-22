import React, { useEffect, useState } from "react";
import { Routes, Route, Link, useLocation, useNavigate } from "react-router-dom";
import { Bot, Upload, Activity, LogOut } from "lucide-react";
import ChatPage from "./pages/ChatPage";
import UploadPage from "./pages/UploadPage";
import HealthBadge from "./components/HealthBadge";
import ThemeToggle from "./components/ThemeToggle";
import ToastContainer, { pushToast } from "./components/ToastContainer";
import AuthPanel from "./components/AuthPanel";
import { getCurrentUser } from "./api";

const TOKEN_KEY = "medibot_auth_token";

function AppContent() {
  const location = useLocation();
  const navigate = useNavigate();
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) || "");
  const [user, setUser] = useState(null);
  const [authReady, setAuthReady] = useState(false);

  useEffect(() => {
    if (!token) {
      setUser(null);
      setAuthReady(true);
      return;
    }

    let mounted = true;
    getCurrentUser(token)
      .then(({ user: currentUser }) => {
        if (mounted) setUser(currentUser);
      })
      .catch(() => {
        localStorage.removeItem(TOKEN_KEY);
        if (mounted) {
          setToken("");
          setUser(null);
        }
      })
      .finally(() => {
        if (mounted) setAuthReady(true);
      });

    return () => {
      mounted = false;
    };
  }, [token]);

  function handleAuth(session) {
    localStorage.setItem(TOKEN_KEY, session.token);
    setToken(session.token);
    setUser(session.user);
    setAuthReady(true);
    navigate("/");
  }

  function handleLogout() {
    localStorage.removeItem(TOKEN_KEY);
    setToken("");
    setUser(null);
    pushToast({ type: "info", title: "Signed out", msg: "Protected features are locked again" });
    navigate("/");
  }

  const getNavLinkClass = (path) => {
    const isActive = location.pathname === path;
    const base = `group relative px-4 py-2 rounded-lg font-medium text-sm transition-all duration-300`;
    const active = isActive
      ? "text-white"
      : "text-gray-700 dark:text-gray-300 hover:text-cyan-600 dark:hover:text-cyan-400";

    return `${base} ${active}`;
  };

  const getNavBgClass = (path) => {
    const isActive = location.pathname === path;
    const gradient =
      path === "/" ? "bg-gradient-to-r from-cyan-500 to-blue-600" : "bg-gradient-to-r from-blue-500 to-indigo-600";

    return `absolute inset-0 ${gradient} transition-transform duration-300 ${
      isActive ? "scale-100" : "scale-0 group-hover:scale-100"
    }`;
  };

  return (
    <div className="min-h-screen transition-colors duration-700 bg-gradient-to-br from-white via-blue-50 to-blue-100 dark:from-slate-950 dark:via-blue-950 dark:to-cyan-950">
      <header className="bg-white/70 dark:bg-slate-900/70 backdrop-blur-lg shadow-lg border-b border-gray-200 dark:border-cyan-500/20 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-4 group">
              <div className="relative">
                <div className="absolute inset-0 bg-gradient-to-r from-cyan-500 to-blue-600 rounded-xl blur-md opacity-70 group-hover:opacity-100 transition-opacity duration-300"></div>
                <div className="relative w-14 h-14 bg-gradient-to-br from-cyan-600 via-blue-600 to-indigo-700 rounded-xl flex items-center justify-center shadow-lg group-hover:scale-110 transition-transform duration-300">
                  <Bot className="w-8 h-8 text-white" strokeWidth={2.5} />
                </div>
              </div>

              <div>
                <h1 className="text-2xl font-bold bg-gradient-to-r from-cyan-600 to-blue-600 dark:from-cyan-400 dark:to-blue-400 bg-clip-text text-transparent flex items-center gap-2">
                  MediBot AI
                  <Activity className="w-5 h-5 text-cyan-500 animate-pulse" />
                </h1>
                <p className="text-sm text-gray-600 dark:text-gray-400 font-medium">
                  Advanced Medical Intelligence System • RAG Optimized
                </p>
              </div>
            </div>

            <nav className="flex items-center gap-3 flex-wrap justify-end">
              <Link to="/" className={getNavLinkClass("/")}>
                <span className={getNavBgClass("/")}></span>
                <span className="relative flex items-center gap-2">
                  <Bot className="w-4 h-4" />
                  Chat
                </span>
              </Link>

              <Link to="/upload" className={getNavLinkClass("/upload")}>
                <span className={getNavBgClass("/upload")}></span>
                <span className="relative flex items-center gap-2">
                  <Upload className="w-4 h-4" />
                  Upload
                </span>
              </Link>

              <div className="h-8 w-px bg-gray-300 dark:bg-gray-700 mx-1"></div>

              <HealthBadge />
              <ThemeToggle />

              {user ? (
                <div className="flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50/80 px-3 py-2 text-xs dark:border-emerald-700/40 dark:bg-emerald-950/30">
                  <div className="text-emerald-800 dark:text-emerald-200">
                    <div className="font-semibold">{user.name || user.email}</div>
                    <div className="text-emerald-700 dark:text-emerald-300">{user.email}</div>
                  </div>
                  <button
                    type="button"
                    onClick={handleLogout}
                    className="inline-flex items-center gap-1 rounded-md border border-emerald-300 px-2 py-1 font-semibold text-emerald-800 transition hover:bg-emerald-100 dark:border-emerald-700 dark:text-emerald-200 dark:hover:bg-emerald-900/40"
                  >
                    <LogOut className="h-3.5 w-3.5" />
                    Sign out
                  </button>
                </div>
              ) : null}
            </nav>
          </div>
        </div>

        <div className="absolute bottom-0 left-0 right-0 h-1 bg-gradient-to-r from-cyan-500 via-blue-500 to-indigo-600 opacity-70"></div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-8 relative">
        <div className={!user && authReady ? "pointer-events-none select-none blur-md" : ""}>
          <Routes>
            <Route path="/" element={<ChatPage token={token} user={user} onLogout={handleLogout} />} />
            <Route path="/upload" element={<UploadPage token={token} />} />
          </Routes>
        </div>

        {!user && authReady ? (
          <div className="absolute inset-0 z-20 flex items-center justify-center px-4">
            <AuthPanel user={user} token={token} onAuth={handleAuth} onLogout={handleLogout} overlay />
          </div>
        ) : null}
      </main>

      <footer className="text-center text-sm text-gray-600 dark:text-gray-400 py-8 border-t border-gray-200 dark:border-gray-800">
        <div className="flex items-center justify-center gap-2 mb-2">
          <div className="w-2 h-2 bg-cyan-500 rounded-full animate-pulse"></div>
          <span className="font-medium">Tactical Medical Intelligence Platform</span>
          <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse"></div>
        </div>

        <div className="text-xs">
          Backend API: <code className="bg-gray-100 dark:bg-slate-800 px-2 py-1 rounded">/api</code>
        </div>
      </footer>

      <ToastContainer />
    </div>
  );
}

export default function App() {
  return <AppContent />;
}
