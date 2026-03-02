// components/AnimatedPageWrapper.jsx
import React from "react";

export default function AnimatedPageWrapper({ children }) {
  return (
    <div className="animate-in fade-in duration-500 slide-in-from-bottom-2">
      {children}
    </div>
  );
}
