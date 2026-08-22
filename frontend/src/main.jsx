// main.jsx
import React from "react"
import { createRoot } from "react-dom/client"
import { BrowserRouter } from "react-router-dom"
import App from "./App"
import "./styles/tailwind.css"
import ErrorBoundary from "./components/ErrorBoundary"

// IMPORT REAL ThemeProvider (NOT ThemeContext, NOT redefined)
import { ThemeProvider } from "./context/ThemeContext"

const root = createRoot(document.getElementById("root"))

root.render(
  <React.StrictMode>
    <BrowserRouter>
      <ThemeProvider>
        <ErrorBoundary>
          <App />
        </ErrorBoundary>
      </ThemeProvider>
    </BrowserRouter>
  </React.StrictMode>
)
