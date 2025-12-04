import React from "react";
import { Trash2, Database, Brain, Shield } from "lucide-react";

export default function ModeSelector({ mode, setMode, clearHistory }) {
  const modeConfig = {
    basic: {
      icon: Database,
      label: "Basic RAG",
      desc: "Semantic retrieval over uploaded PDFs.",
      bgColor: "bg-blue-500/10 dark:bg-blue-500/20",
      borderColor: "border-blue-500/40",
      color: "from-blue-600 to-cyan-600",
    },
    optimized: {
      icon: Brain,
      label: "Optimized RAG",
      desc: "Enhanced retrieval + reasoning.",
      bgColor: "bg-purple-500/10 dark:bg-purple-500/20",
      borderColor: "border-purple-500/40",
      color: "from-purple-600 to-pink-600",
    },
  };

  return (
    <div className="lg:col-span-1 space-y-4">
      <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-xl 
                      border-2 border-gray-200 dark:border-cyan-500/20 p-6">

        <div className="flex items-center gap-3 mb-6">
          <div className="p-2 bg-gradient-to-br from-cyan-500 to-blue-600 rounded-lg">
            <Brain className="w-5 h-5 text-white" />
          </div>
          <h3 className="font-bold text-lg text-gray-900 dark:text-white">
            RAG Mode
          </h3>
        </div>

        <div className="space-y-3">
          {Object.entries(modeConfig).map(([key, cfg]) => {
            const Icon = cfg.icon;
            const active = mode === key;

            return (
              <button
                key={key}
                onClick={() => setMode(key)}
                className={`w-full text-left p-4 rounded-xl border-2 transition-all duration-300 
                    ${
                      active
                        ? `${cfg.bgColor} ${cfg.borderColor} shadow-lg scale-105`
                        : "border-gray-200 dark:border-gray-700 hover:border-cyan-400 dark:hover:border-cyan-500 hover:shadow-md"
                    }`}
              >
                <div className="flex items-center gap-3 mb-2">
                  <Icon
                    className={`w-5 h-5 ${
                      active
                        ? "text-cyan-600 dark:text-cyan-400"
                        : "text-gray-500 dark:text-gray-400"
                    }`}
                  />
                  <span
                    className={`font-semibold ${
                      active
                        ? "text-gray-900 dark:text-white"
                        : "text-gray-700 dark:text-gray-300"
                    }`}
                  >
                    {cfg.label}
                  </span>
                </div>
                <p className="text-xs text-gray-600 dark:text-gray-400 pl-8">
                  {cfg.desc}
                </p>
              </button>
            );
          })}
        </div>

        <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
          <button
            onClick={clearHistory}
            className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl
                     bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400
                     border-2 border-red-200 dark:border-red-500/30
                     hover:bg-red-100 dark:hover:bg-red-900/30 hover:scale-105
                     transition-all duration-200 font-semibold"
          >
            <Trash2 className="w-4 h-4" />
            Clear History
          </button>
        </div>

        <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
            <Shield className="w-4 h-4" />
            <span>Secure • Private • Encrypted</span>
          </div>
        </div>
      </div>
    </div>
  );
}
