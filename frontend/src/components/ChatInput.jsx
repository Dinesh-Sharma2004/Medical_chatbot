// ChatInput.jsx
import React from "react";
import { Lock, Send, X } from "lucide-react";

export default function ChatInput({ input, setInput, loading, onSubmit, onCancel, disabled = false }) {
  return (
    <div className="p-6 bg-white dark:bg-slate-900 border-t-2 border-gray-200 dark:border-cyan-500/20">
      <div className="flex gap-4">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && !disabled && onSubmit()}
          placeholder={disabled ? "Sign in to ask medical questions" : "Type your medical question..."}
          disabled={loading || disabled}
          className="flex-1 px-6 py-4 rounded-xl border-2 border-gray-300 dark:border-gray-700
           bg-gray-50 dark:bg-slate-800 text-gray-900 dark:text-white
           focus:border-cyan-500 dark:focus:border-cyan-400 focus:ring-4 focus:ring-cyan-500/20
           transition-all duration-200 outline-none text-lg
           placeholder-gray-400 dark:placeholder-gray-500 shadow-inner"
        />

        {!loading ? (
          <button
            onClick={onSubmit}
            disabled={!input.trim() || disabled}
            className="group relative px-8 py-4 rounded-xl font-bold text-white text-lg
                       bg-gradient-to-r from-cyan-500 via-blue-500 to-indigo-600
                       hover:shadow-2xl hover:shadow-cyan-500/30 hover:scale-105 active:scale-98
                       transition-all duration-300 overflow-hidden min-w-[140px] border border-white/10"
          >
            <span className="relative z-10 flex items-center gap-2">
              <Send className="w-6 h-6" /> Send
            </span>
          </button>
        ) : (
          <button
            onClick={onCancel}
            className="px-8 py-4 rounded-xl bg-gradient-to-r from-red-600 to-pink-600 hover:from-red-500 hover:to-pink-500
                       text-white font-bold text-lg hover:shadow-2xl hover:shadow-red-500/30
                       transform hover:scale-105 active:scale-98 transition-all duration-300
                       flex items-center justify-center gap-2 min-w-[140px]"
          >
            <X className="w-6 h-6" /> Stop
          </button>
        )}
      </div>

      <div className="flex items-center justify-between mt-4 text-xs text-gray-500 dark:text-gray-400">
        <span className="flex items-center gap-2">
          {disabled ? <Lock className="w-3.5 h-3.5" /> : null}
          {disabled ? "Authentication required" : "Press Enter to send • Shift + Enter for new line"}
        </span>
        <span>{input.length} / 2000 characters</span>
      </div>
    </div>
  );
}
