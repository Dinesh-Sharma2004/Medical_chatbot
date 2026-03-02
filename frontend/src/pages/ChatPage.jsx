import React, { useEffect, useState, useRef, useCallback } from "react";
import { health } from "../api";
import { pushToast } from "../components/ToastContainer";
import ModeSelector from "../components/ModeSelector";
import ChatInput from "../components/ChatInput";
import EmptyState from "../components/EmptyState";
import { useAskStream } from "../hooks/useAskStream";
import { Sparkles, Database, ExternalLink, ArrowDown } from "lucide-react";

const STORAGE_KEY = "medibot_conversation_v1";

export default function ChatPage() {
  const [messages, setMessages] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    } catch {
      return [];
    }
  });

  const [mode, setMode] = useState("basic");
  const [input, setInput] = useState("");
  const { ask, answer, isLoading, sources, cancel, setAnswer } = useAskStream();

  const chatRef = useRef(null);
  const scrollLockRef = useRef(false);
  const [showScrollButton, setShowScrollButton] = useState(false);

  // Persist chat
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
  }, [messages]);

  const filteredMessages = messages.filter((m) => (m.mode || "basic") === mode);

  useEffect(() => {
    health().catch(() => console.warn("Health check failed"));
  }, []);

  // Scrolling
  const scrollToBottom = useCallback((smooth = true) => {
    const el = chatRef.current;
    if (!el) return;
    el.scrollTo({
      top: el.scrollHeight,
      behavior: smooth ? "smooth" : "auto",
    });
  }, []);

  const handleScroll = useCallback(() => {
    const el = chatRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 50;
    scrollLockRef.current = !atBottom;
    setShowScrollButton(!atBottom);
  }, []);

  useEffect(() => {
    const el = chatRef.current;
    if (!el) return;
    el.addEventListener("scroll", handleScroll);
    return () => el.removeEventListener("scroll", handleScroll);
  }, [handleScroll]);

  // Observe message changes for auto-scroll
  useEffect(() => {
    const el = chatRef.current;
    if (!el) return;
    const observer = new MutationObserver(() => {
      if (!scrollLockRef.current) scrollToBottom(true);
    });
    observer.observe(el, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [scrollToBottom]);

  // === 🔹 Streaming updates without removing previous ===
  useEffect(() => {
    if (!isLoading || answer == null) return;
    setMessages((prev) =>
      prev.map((m) =>
        m.streaming && (m.mode || "basic") === mode
          ? { ...m, text: answer }
          : m
      )
    );
  }, [answer, isLoading, mode]);

  // === 🔹 After streaming completes ===
  useEffect(() => {
    if (isLoading) return;
    if (!answer?.trim()) {
      setAnswer("");
      return;
    }

    const cleanSources = (sources || []).map((s) => ({
      page: s.page || s.page_number || s.p,
      filename: s.filename,
      sourcePath: s.source || s.source_path,
    }));

    setMessages((prev) => {
      const updated = prev.map((msg) =>
        msg.streaming && (msg.mode || "basic") === mode
          ? {
              ...msg,
              text: answer.trim(),
              streaming: false,
              sources: cleanSources,
            }
          : msg
      );
      return updated;
    });

    setAnswer("");
    setTimeout(() => scrollToBottom(false), 100);
  }, [isLoading]);

  // === 🔹 Send Message ===
  async function sendMessage() {
    const question = input.trim();
    if (!question) return;

    const userMsg = {
      id: Date.now() + "-user",
      role: "user",
      text: question,
      mode,
    };
    const botPlaceholder = {
      id: Date.now() + "-bot-stream",
      role: "bot",
      text: "",
      streaming: true,
      mode,
      sources: [],
    };

    setMessages((prev) => [...prev, userMsg, botPlaceholder]);
    setInput("");

    await new Promise((r) => setTimeout(r, 50));

    try {
      await ask(question, mode);
    } catch (err) {
      console.error(err);
      pushToast({ type: "error", title: "Error", msg: "Streaming failed" });
    }
  }

  function clearHistory() {
    setMessages([]);
    localStorage.removeItem(STORAGE_KEY);
    pushToast({ type: "info", title: "Cleared", msg: "Conversation cleared" });
  }

  // === 🔹 Open PDF Source Page ===
  function openPdfAtPage(sourcePath, page) {
    if (!sourcePath) return;
    const url = `${sourcePath}#page=${page || 1}`;
    window.open(url, "_blank");
  }

  return (
    <div className="w-full max-w-7xl mx-auto h-[calc(100vh-130px)] flex flex-col">
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 flex-1 min-h-0">
        <ModeSelector mode={mode} setMode={setMode} clearHistory={clearHistory} />

        {/* Chat Column */}
        <div className="lg:col-span-3 flex flex-col h-full min-h-0 relative">
          <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border-2 
                          border-gray-200 dark:border-cyan-500/20 flex flex-col flex-1 min-h-0">

            {/* Header */}
            <div
              className={`bg-gradient-to-r ${
                mode === "basic"
                  ? "from-blue-600 to-cyan-600"
                  : "from-purple-600 to-pink-600"
              } p-4`}
            >
              <div className="flex items-center gap-3">
                <div className="p-2 bg-white/20 rounded-xl backdrop-blur-sm shadow-md">
                  {mode === "basic" ? (
                    <Database className="w-5 h-5 text-white" />
                  ) : (
                    <Sparkles className="w-5 h-5 text-white" />
                  )}
                </div>
                <div>
                  <h2 className="text-lg font-bold text-white flex items-center gap-2">
                    MediBot – Medical RAG Assistant
                    <Sparkles className="w-4 h-4 animate-pulse" />
                  </h2>
                  <p className="text-xs text-white/90 font-medium">
                    {mode === "basic" ? "Basic RAG" : "Optimized RAG"} •{" "}
                    {filteredMessages.length} messages
                  </p>
                </div>
              </div>
            </div>

            {/* Chat Messages */}
            <div
              ref={chatRef}
              className="flex-1 overflow-y-auto overflow-x-hidden p-5 space-y-5 
                         bg-gradient-to-b from-gray-50/60 to-white dark:from-slate-950/60 dark:to-slate-900"
            >
              {filteredMessages.length === 0 && <EmptyState />}

              {filteredMessages.map((m) => (
                <div key={m.id} className="flex flex-col">
                  <div
                    className={`max-w-[85%] md:max-w-[75%] rounded-2xl px-4 py-3 shadow-sm 
                      ${
                        m.role === "user"
                          ? "ml-auto bg-gradient-to-r from-cyan-500 to-blue-600 text-white"
                          : "mr-auto bg-gray-100 dark:bg-slate-800 text-gray-800 dark:text-gray-100"
                      } ${m.streaming ? "streaming-placeholder" : ""}`}
                  >
                    <p className="whitespace-pre-line text-[15px] leading-relaxed">
                      {m.text || (m.streaming ? "MediBot is thinking…" : "")}
                    </p>
                  </div>

                  {/* === 🔹 Source Page Buttons === */}
                  {m.role === "bot" &&
                    Array.isArray(m.sources) &&
                    m.sources.length > 0 && (
                      <div className="flex flex-wrap gap-2 mt-2 ml-1">
                        {m.sources.map(
                          (s, i) =>
                            s.page && (
                              <button
                                key={i}
                                onClick={() => openPdfAtPage(s.sourcePath, s.page)}
                                className="text-xs font-medium text-cyan-700 dark:text-cyan-400 
                                           hover:underline flex items-center gap-1 bg-cyan-50/60 
                                           dark:bg-slate-800/60 px-2 py-1 rounded-full border border-cyan-200/30 
                                           dark:border-cyan-600/30 transition-all duration-200 hover:bg-cyan-100/60"
                                title={`Open ${s.filename || "document"} page ${s.page}`}
                              >
                                p.{s.page}
                                <ExternalLink className="w-3 h-3 opacity-70" />
                              </button>
                            )
                        )}
                      </div>
                    )}
                </div>
              ))}
            </div>

            {/* Chat Input */}
            <div className="border-t border-gray-200 dark:border-cyan-500/20 bg-white/70 dark:bg-slate-900/70">
              <ChatInput
                input={input}
                setInput={setInput}
                loading={isLoading}
                onSubmit={sendMessage}
                onCancel={cancel}
              />
            </div>
          </div>

          {/* Scroll Button */}
          {showScrollButton && (
            <button
              onClick={() => {
                scrollLockRef.current = false;
                scrollToBottom(true);
              }}
              className="absolute bottom-24 right-6 p-3 rounded-full bg-gradient-to-r 
                         from-cyan-500 to-blue-600 text-white shadow-lg hover:scale-110 
                         transition-all duration-300 border border-white/30 dark:border-slate-700/40"
              title="Scroll to latest message"
            >
              <ArrowDown className="w-5 h-5" />
            </button>
          )}
        </div>
      </div>

      <style>{`
        .streaming-placeholder {
          animation: pulse-ellipsis 1.5s infinite steps(4, end);
        }
        @keyframes pulse-ellipsis {
          0% { opacity: 1; }
          50% { opacity: 0.6; }
          100% { opacity: 1; }
        }
      `}</style>
    </div>
  );
}
