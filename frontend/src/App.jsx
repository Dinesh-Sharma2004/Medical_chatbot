import React from "react"
import { Routes, Route, Link, useLocation } from "react-router-dom"
import ChatPage from "./pages/ChatPage"
import UploadPage from "./pages/UploadPage"
import HealthBadge from "./components/HealthBadge"
import ThemeToggle from "./components/ThemeToggle"
import ToastContainer from "./components/ToastContainer"
import { ThemeProvider } from "./context/ThemeContext"
import { Bot, Upload, Activity } from "lucide-react"

function AppContent() {
  const location = useLocation()

  const getNavLinkClass = (path) => {
    const isActive = location.pathname === path
    const base = `group relative px-4 py-2 rounded-lg font-medium text-sm
                  transition-all duration-300`
    const active = isActive
      ? "text-white"
      : "text-gray-700 dark:text-gray-300 hover:text-cyan-600 dark:hover:text-cyan-400"

    return `${base} ${active}`
  }

  const getNavBgClass = (path) => {
    const isActive = location.pathname === path
    const gradient =
      path === "/" ? "bg-gradient-to-r from-cyan-500 to-blue-600" : "bg-gradient-to-r from-blue-500 to-indigo-600"

    return `absolute inset-0 ${gradient} transition-transform duration-300 ${
      isActive ? "scale-100" : "scale-0 group-hover:scale-100"
    }`
  }

  return (
    <div
      className="min-h-screen transition-colors duration-700 
                 bg-gradient-to-br from-white via-blue-50 to-blue-100 
                 dark:from-slate-950 dark:via-blue-950 dark:to-cyan-950"
    >
      {/* HEADER */}
      <header className="bg-white/70 dark:bg-slate-900/70 backdrop-blur-lg shadow-lg 
                         border-b border-gray-200 dark:border-cyan-500/20 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            {/* Branding */}
            <div className="flex items-center gap-4 group">
              <div className="relative">
                <div className="absolute inset-0 bg-gradient-to-r from-cyan-500 to-blue-600 
                                rounded-xl blur-md opacity-70 group-hover:opacity-100 
                                transition-opacity duration-300"></div>
                <div className="relative w-14 h-14 bg-gradient-to-br from-cyan-600 via-blue-600 to-indigo-700 
                                rounded-xl flex items-center justify-center shadow-lg 
                                group-hover:scale-110 transition-transform duration-300">
                  <Bot className="w-8 h-8 text-white" strokeWidth={2.5} />
                </div>
              </div>

              <div>
                <h1 className="text-2xl font-bold bg-gradient-to-r from-cyan-600 to-blue-600 
                               dark:from-cyan-400 dark:to-blue-400 bg-clip-text text-transparent flex items-center gap-2">
                  MediBot AI
                  <Activity className="w-5 h-5 text-cyan-500 animate-pulse" />
                </h1>
                <p className="text-sm text-gray-600 dark:text-gray-400 font-medium">
                  Advanced Medical Intelligence System • RAG Optimized
                </p>
              </div>
            </div>

            {/* Nav */}
            <nav className="flex items-center gap-3">
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

              <div className="h-8 w-px bg-gray-300 dark:bg-gray-700 mx-2"></div>

              <HealthBadge />
              <ThemeToggle />
            </nav>
          </div>
        </div>

        {/* Header Bottom Glow */}
        <div className="absolute bottom-0 left-0 right-0 h-1 bg-gradient-to-r 
                       from-cyan-500 via-blue-500 to-indigo-600 opacity-70"></div>
      </header>

      {/* MAIN */}
      <main className="max-w-7xl mx-auto px-4 py-8">
        <Routes>
          <Route path="/" element={<ChatPage />} />
          <Route path="/upload" element={<UploadPage />} />
        </Routes>
      </main>

      {/* FOOTER */}
      <footer
        className="text-center text-sm text-gray-600 dark:text-gray-400 py-8 
                   border-t border-gray-200 dark:border-gray-800"
      >
        <div className="flex items-center justify-center gap-2 mb-2">
          <div className="w-2 h-2 bg-cyan-500 rounded-full animate-pulse"></div>
          <span className="font-medium">Tactical Medical Intelligence Platform</span>
          <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse"></div>
        </div>

        <div className="text-xs">
          Backend API:{" "}
          <code className="bg-gray-100 dark:bg-slate-800 px-2 py-1 rounded">/api</code>
        </div>
      </footer>

      <ToastContainer />
    </div>
  )
}

export default function App() {
  return (
    <ThemeProvider>
      <AppContent />
    </ThemeProvider>
  )
}
