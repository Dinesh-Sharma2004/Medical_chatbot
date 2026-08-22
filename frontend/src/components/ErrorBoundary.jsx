import React from "react";

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    // Keep a console trace for local debugging.
    console.error("React render crash:", error, info);
  }

  render() {
    if (!this.state.hasError) return this.props.children;
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "grid",
          placeItems: "center",
          background: "#0f172a",
          color: "#e2e8f0",
          padding: "24px",
          fontFamily: "ui-sans-serif, system-ui, sans-serif",
        }}
      >
        <div style={{ maxWidth: 900, width: "100%" }}>
          <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 12 }}>
            Frontend Runtime Error
          </h1>
          <p style={{ marginBottom: 10 }}>
            App render ke dauraan error aaya. Neeche exact message hai:
          </p>
          <pre
            style={{
              whiteSpace: "pre-wrap",
              background: "#020617",
              border: "1px solid #334155",
              borderRadius: 8,
              padding: 12,
              overflowX: "auto",
            }}
          >
            {String(this.state.error?.stack || this.state.error?.message || this.state.error || "Unknown error")}
          </pre>
        </div>
      </div>
    );
  }
}
