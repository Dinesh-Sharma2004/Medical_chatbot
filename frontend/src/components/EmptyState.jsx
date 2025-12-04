import React from "react";
import { Database } from "lucide-react";

export default function EmptyState() {
  return (
    <div className="h-full flex items-center justify-center p-8">
      <div className="text-center space-y-6 max-w-2xl">
        <div className="relative inline-block animate-float">
          <div className="absolute inset-0 bg-gradient-to-r from-cyan-500 via-blue-500 
                          to-purple-500 rounded-3xl blur-3xl opacity-30 animate-pulse"></div>
          <div className="relative p-8 bg-gradient-to-br from-cyan-500 via-blue-600 
                          to-indigo-700 rounded-3xl shadow-2xl">
            <Database className="w-20 h-20 text-white" />
          </div>
        </div>

        <h3 className="text-3xl font-bold bg-gradient-to-r from-cyan-600 via-blue-600 to-purple-600 
                     dark:from-cyan-400 dark:via-blue-400 dark:to-purple-400 bg-clip-text text-transparent">
          Medical RAG Ready
        </h3>

        <p className="text-gray-600 dark:text-gray-400 text-lg">
          Ask any medical question. Upload PDFs first to unlock powerful retrieval-augmented answers.
        </p>
      </div>
    </div>
  );
}
