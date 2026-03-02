// ChatInput.jsx
import React from "react";
import { Send, X } from "lucide-react";

export default function ChatInput({ input, setInput, loading, onSubmit, onCancel }) {
  return (
    <div className="p-6 bg-white dark:bg-slate-900 border-t-2 border-gray-200 dark:border-cyan-500/20">
      <div className="flex gap-4">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && onSubmit()}
          placeholder="Type your medical question..."
          disabled={loading}
          className="flex-1 px-6 py-4 rounded-xl border-2 border-gray-300 dark:border-gray-700
           bg-gray-50 dark:bg-slate-800 text-gray-900 dark:text-white
           focus:border-cyan-500 dark:focus:border-cyan-400 focus:ring-4 focus:ring-cyan-500/20
           transition-all duration-200 outline-none text-lg
           placeholder-gray-400 dark:placeholder-gray-500 shadow-inner"
        />

        {!loading ? (
          <button
            onClick={onSubmit}
            disabled={!input.trim()}
            className="group relative px-8 py-4 rounded-xl font-bold text-white text-lg
                       bg-gradient-to-r from-cyan-600 to-blue-600
                       hover:shadow-2xl hover:shadow-cyan-500/30
                       transform hover:scale-105 active:scale-95
                       transition-all duration-200 overflow-hidden min-w-[140px]"
          >
            <span className="relative z-10 flex items-center gap-2">
              <Send className="w-6 h-6" /> Send
            </span>
          </button>
        ) : (
          <button
            onClick={onCancel}
            className="px-6 py-4 rounded-xl bg-red-600 text-white font-semibold hover:bg-red-500"
          >
            <X className="w-6 h-6" />
          </button>
        )}
      </div>

      <div className="flex items-center justify-between mt-4 text-xs text-gray-500 dark:text-gray-400">
        <span>Press Enter to send • Shift + Enter for new line</span>
        <span>{input.length} / 2000 characters</span>
      </div>
    </div>
  );
}
