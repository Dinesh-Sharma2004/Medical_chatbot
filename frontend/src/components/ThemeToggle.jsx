// ThemeToggle.jsx
import React from "react"
import "../styles/reduced-motion.css";
import { Moon, Sun } from "lucide-react"
import { useTheme } from "../context/ThemeContext"

export default function ThemeToggle() {
  const { theme, toggleTheme } = useTheme()
  const isDark = theme === "dark"

  return (
    <button
      onClick={toggleTheme}
      aria-label="Toggle theme"
      aria-pressed={isDark}
      title={`Switch to ${isDark ? "light" : "dark"} mode`}
      className="relative group p-2 rounded-xl border border-gray-300 dark:border-cyan-500/40 
                 bg-gradient-to-br from-gray-100 to-gray-200 dark:from-slate-800 dark:to-slate-900
                 shadow-sm hover:shadow-md hover:scale-110 active:scale-95
                 transition-all duration-300 
                 focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400 dark:focus-visible:ring-cyan-500"
    >
      <div className="relative w-6 h-6">
        <Sun
          className={`absolute inset-0 w-6 h-6 text-yellow-500 transform transition-all duration-500
                     ${isDark ? "rotate-90 scale-0 opacity-0" : "rotate-0 scale-100 opacity-100"}`}
        />
        <Moon
          className={`absolute inset-0 w-6 h-6 text-cyan-400 transform transition-all duration-500
                     ${isDark ? "rotate-0 scale-100 opacity-100" : "-rotate-90 scale-0 opacity-0"}`}
        />
      </div>

      <div
        className="absolute inset-0 rounded-xl bg-gradient-to-r from-cyan-500/0 via-cyan-500/20 to-cyan-500/0 
                    opacity-0 group-hover:opacity-100 transition-opacity duration-300 blur-sm -z-10"
      ></div>

    </button>
  )
}
