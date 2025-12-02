// Message.jsx
import React from "react"
import { User, Bot, ExternalLink, FileText, Link as LinkIcon } from "lucide-react"

export default function Message({ role, text, sources = [], mode, index = 0 }) {
  const isUser = role === "user"

  const modeStyles = {
    basic: {
      label: "📘 Basic RAG",
      className:
        "bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400",
    },
    optimized: {
      label: "🧠 Optimized RAG",
      className:
        "bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-400",
    },
    // Fallbacks if backend ever sends these
    auto: {
      label: "⚡ Auto Mode",
      className:
        "bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400",
    },
    rag: {
      label: "📚 RAG Mode",
      className:
        "bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400",
    },
    web: {
      label: "🌐 Web Search",
      className:
        "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400",
    },
  }

  const badge = mode ? modeStyles[mode] || null : null

  return (
    <div
      className={`flex items-start gap-4 animate-in fade-in slide-in-from-${
        isUser ? "right" : "left"
      }-4 duration-500`}
      style={{ animationDelay: `${index * 50}ms` }}
    >
      {!isUser && (
        <div className="flex-shrink-0 relative group">
          <div className="absolute inset-0 bg-gradient-to-br from-cyan-500 to-blue-600 rounded-xl blur-md opacity-70 group-hover:opacity-100 transition-opacity"></div>
          <div className="relative p-3 bg-gradient-to-br from-cyan-500 to-blue-600 rounded-xl shadow-xl">
            <Bot className="w-6 h-6 text-white" strokeWidth={2.5} />
          </div>
        </div>
      )}

      <div className={`flex-1 ${isUser ? "flex justify-end" : ""}`}>
        <div
          className={`max-w-[85%] ${
            isUser
              ? "bg-gradient-to-br from-indigo-600 via-purple-600 to-pink-600 text-white rounded-2xl rounded-tr-sm shadow-xl border-2 border-indigo-400"
              : "bg-white dark:bg-slate-800 text-gray-900 dark:text-white rounded-2xl rounded-tl-sm shadow-xl border-2 border-cyan-200 dark:border-cyan-500/30"
          } p-5 transition-all duration-200 hover:shadow-2xl`}
        >
          {/* Message Text */}
          <div
            className={`whitespace-pre-wrap break-words leading-relaxed text-base ${
              isUser
                ? "text-white"
                : "text-gray-800 dark:text-gray-100"
            }`}
          >
            {text}
          </div>

          {/* Mode Badge */}
          {!isUser && badge && (
            <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
              <div
                className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg font-bold text-xs uppercase tracking-wide ${badge.className}`}
              >
                {badge.label}
              </div>
            </div>
          )}

          {/* Sources */}
          {!isUser && sources.length > 0 && (
            <div className="mt-5 pt-5 border-t-2 border-gray-200 dark:border-gray-700 space-y-3">
              <div className="flex items-center gap-2 mb-3">
                <FileText className="w-4 h-4 text-cyan-600 dark:text-cyan-400" />
                <span className="text-sm font-bold text-gray-700 dark:text-gray-300 uppercase tracking-wide">
                  Sources ({sources.length})
                </span>
              </div>

              <div className="space-y-3">
                {sources.map((s, i) => (
                  <div
                    key={i}
                    className="group relative p-4 rounded-xl bg-gradient-to-br from-gray-50 to-blue-50 dark:from-slate-900/50 dark:to-slate-800/50 
                               border-2 border-gray-200 dark:border-gray-700
                               hover:border-cyan-400 dark:hover:border-cyan-500 
                               transition-all duration-300 hover:shadow-lg hover:scale-[1.02]"
                  >
                    <div className="flex items-start gap-3">
                      <div className="flex-shrink-0 p-2 bg-cyan-100 dark:bg-cyan-900/30 rounded-lg">
                        <LinkIcon className="w-4 h-4 text-cyan-600 dark:text-cyan-400" />
                      </div>

                      <div className="flex-1 min-w-0 space-y-2">
                        <div className="flex items-start justify-between gap-2">
                          <h4 className="text-sm font-bold text-gray-900 dark:text-white truncate">
                            {s.title ?? s.name ?? `Source ${i + 1}`}
                          </h4>
                          <span className="flex-shrink-0 text-xs font-medium text-cyan-600 dark:text-cyan-400 bg-cyan-50 dark:bg-cyan-900/20 px-2 py-1 rounded-md">
                            #{i + 1}
                          </span>
                        </div>

                        {(s.snippet || s.text) && (
                          <p className="text-sm text-gray-600 dark:text-gray-400 line-clamp-3 leading-relaxed">
                            {s.snippet ?? s.text}
                          </p>
                        )}

                        {s.url && (
                          <a
                            href={s.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-xs font-medium text-cyan-600 dark:text-cyan-400 hover:text-cyan-700 dark:hover:text-cyan-300 hover:underline"
                          >
                            <ExternalLink className="w-3 h-3" />
                            Visit source
                          </a>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {isUser && (
        <div className="flex-shrink-0 relative group">
          <div className="absolute inset-0 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-xl blur-md opacity-70 group-hover:opacity-100 transition-opacity"></div>
          <div className="relative p-3 bg-gradient-to-br from-indigo-600 to-purple-600 rounded-xl shadow-xl">
            <User className="w-6 h-6 text-white" strokeWidth={2.5} />
          </div>
        </div>
      )}
    </div>
  )
}
