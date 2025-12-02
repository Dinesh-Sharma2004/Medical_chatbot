// ThemeContext.jsx
import React, { createContext, useContext, useState, useEffect } from "react"

const ThemeContext = createContext()

export function useTheme() {
  const context = useContext(ThemeContext)
  if (!context) {
    throw new Error("useTheme must be used within ThemeProvider")
  }
  return context
}

export function ThemeProvider({ children }) {
  const getSystemTheme = () =>
    window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"

  const getInitialTheme = () => {
    if (typeof window === "undefined") return "light"
    const saved = localStorage.getItem("medibot-theme")
    if (saved) return saved
    return getSystemTheme()
  }

  const [theme, setTheme] = useState(getInitialTheme)

  useEffect(() => {
    const root = document.documentElement
    root.classList.remove("light", "dark")
    root.classList.add(theme)
    localStorage.setItem("medibot-theme", theme)
  }, [theme])

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)")
    const handler = () => {
      const saved = localStorage.getItem("medibot-theme")
      if (!saved) {
        setTheme(media.matches ? "dark" : "light")
      }
    }
    media.addEventListener("change", handler)
    return () => media.removeEventListener("change", handler)
  }, [])

  const toggleTheme = () =>
    setTheme((prev) => (prev === "dark" ? "light" : "dark"))

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}
