import React, { useEffect, useState, useRef, useCallback } from "react";
import { health, fetchSourcePdf } from "../api";
import { pushToast } from "../components/ToastContainer";
import ModeSelector from "../components/ModeSelector";
import ChatInput from "../components/ChatInput";
import EmptyState from "../components/EmptyState";
import { useAskStream } from "../hooks/useAskStream";
import { Sparkles, Database, ExternalLink, ArrowDown, LoaderCircle } from "lucide-react";

const STORAGE_KEY = "medibot_conversation_v1";

export default function ChatPage({ token }) {
  const [messages, setMessages] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    } catch {
      return [];
    }
  });

  const [mode, setMode] = useState("basic");
  const [input, setInput] = useState("");
  const { ask, answer, isLoading, sources, cancel, setAnswer } = useAskStream(token);
  const [pdfLoading, setPdfLoading] = useState({});

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
    const cleanRaw = normalizeRawSources(sources);
    setMessages((prev) =>
      prev.map((m) =>
        m.streaming && (m.mode || "basic") === mode
          ? { ...m, text: answer, sources: normalizeSources(sources), rawSources: cleanRaw }
          : m
      )
    );
  }, [answer, sources, isLoading, mode]);

  function sourceCacheKey(source = {}) {
    return `${source.pageKey || source.docId || source.filename || "source"}:${source.page || "?"}`;
  }

  function cleanFilename(name = "") {
    if (!name) return "";
    let clean = name.replace(/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}_(?:\d+_)?/i, "");
    if (clean === name) {
      clean = name.replace(/^[a-fA-F0-9]{32}_(?:\d+_)?/i, "");
    }
    return clean;
  }

  function cleanReasoning(text = "") {
    let clean = text.replace(/<think>[\s\S]*?<\/think>/g, "");
    const thinkIdx = clean.indexOf("<think>");
    if (thinkIdx >= 0) {
      clean = clean.substring(0, thinkIdx);
    }
    return clean;
  }

  function renderFormattedMessage(text, messageSources = []) {
    if (!text) return null;
    let cleanText = cleanReasoning(text);
    
    // Strip [Evidence X] citations
    cleanText = cleanText.replace(/\s*\[Evidence\s*\d+(?:\s*,\s*\d+)*\]/gi, "");
    
    // Strip [p. X] citations
    cleanText = cleanText.replace(/\s*\[p\.?\s*\d+(?:\s*,\s*\d+)*\]/gi, "");
    
    // Clean up any other stray bracketed citations
    cleanText = cleanText.replace(/\s*\[Evidence\s+[^\]]+\]/gi, "");
    cleanText = cleanText.replace(/\s*\[p\.?\s+[^\]]+\]/gi, "");

    return cleanText;
  }

  function normalizeRawSources(items = []) {
    return (items || [])
      .map((s, index) => {
        const page = Number(
          s.page || s.page_number || s.page_label || s.pageLabel || s.p || s.raw_page || 0
        ) || 0;
        return {
          id: `${s.page_key || s.doc_id || s.docId || s.filename || "source"}:${page || index}`,
          page,
          rawPage: s.raw_page,
          pageLabel: s.page_label || s.pageLabel,
          filename: s.filename,
          docId: s.doc_id || s.docId,
          pageKey: s.page_key || s.pageKey,
          citation: s.citation,
          snippet: s.snippet || s.text || "",
          highlight: s.highlight || s.snippet || s.text || "",
          matchScore: s.match_score,
          rank: s.rank,
          score: s.score,
          matchedTerms: Array.isArray(s.matched_terms) ? s.matched_terms : [],
        };
      });
  }

  function normalizeSources(items = []) {
    const seen = new Set();
    return (items || [])
      .map((s, index) => {
        const page = Number(
          s.page || s.page_number || s.page_label || s.pageLabel || s.p || s.raw_page || 0
        ) || 0;
        const normalized = {
          id: `${s.page_key || s.doc_id || s.docId || s.filename || "source"}:${page || index}`,
          page,
          rawPage: s.raw_page,
          pageLabel: s.page_label || s.pageLabel,
          filename: s.filename,
          docId: s.doc_id || s.docId,
          pageKey: s.page_key || s.pageKey,
          citation: s.citation,
          snippet: s.snippet || s.text || "",
          highlight: s.highlight || s.snippet || s.text || "",
          matchScore: s.match_score,
          rank: s.rank,
          score: s.score,
          matchedTerms: Array.isArray(s.matched_terms) ? s.matched_terms : [],
        };
        normalized.cacheKey = sourceCacheKey(normalized);
        return normalized;
      })
      .filter((s) => {
        const key = s.cacheKey;
        if (seen.has(key)) return false;
        seen.add(key);
        return s.page && s.docId;
      });
  }

  // === 🔹 After streaming completes ===
  useEffect(() => {
    if (isLoading) return;
    if (!answer?.trim()) {
      setAnswer("");
      return;
    }

    const cleanSources = normalizeSources(sources);
    const cleanRaw = normalizeRawSources(sources);

    setMessages((prev) => {
      const updated = prev.map((msg) =>
        msg.streaming && (msg.mode || "basic") === mode
          ? {
              ...msg,
              text: answer.trim(),
              streaming: false,
              sources: cleanSources,
              rawSources: cleanRaw,
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
  async function openSourcePdf(source) {
    const key = sourceCacheKey(source);
    if (!source.docId || pdfLoading[key]) return;

    setPdfLoading((prev) => ({ ...prev, [key]: true }));
    try {
      const blob = await fetchSourcePdf(source.docId, token);
      const url = window.URL.createObjectURL(blob);
      const page = Number(source.pageLabel || source.page || 1);
      const targetUrl = `${url}#page=${page}`;
      window.open(targetUrl, "_blank", "noopener,noreferrer");
      window.setTimeout(() => window.URL.revokeObjectURL(url), 60_000);
    } catch (error) {
      pushToast({
        type: "error",
        title: "Source unavailable",
        msg: error?.message || "Failed to open source PDF",
      });
    } finally {
      setPdfLoading((prev) => ({ ...prev, [key]: false }));
    }
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

              {filteredMessages.map((m) => {
                const groupedSources = {};
                if (m.role === "bot" && Array.isArray(m.sources)) {
                  m.sources.forEach((src) => {
                    if (!src.docId) return;
                    if (!groupedSources[src.docId]) {
                      groupedSources[src.docId] = {
                        filename: src.filename || "Uploaded PDF",
                        docId: src.docId,
                        pages: [],
                      };
                    }
                    if (!groupedSources[src.docId].pages.some((p) => p.page === src.page)) {
                      groupedSources[src.docId].pages.push(src);
                    }
                  });
                  Object.values(groupedSources).forEach((group) => {
                    group.pages.sort((a, b) => a.page - b.page);
                  });
                }

                const uniquePagesList = [];
                if (m.role === "bot" && Array.isArray(m.sources)) {
                  const seenKeys = new Set();
                  m.sources.forEach((src) => {
                    const key = `${src.docId}:${src.page}`;
                    if (src.page && src.docId && !seenKeys.has(key)) {
                      seenKeys.add(key);
                      uniquePagesList.push(src);
                    }
                  });
                  uniquePagesList.sort((a, b) => a.page - b.page);
                }

                return (
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
                        {m.role === "bot"
                          ? m.text || m.streaming
                            ? renderFormattedMessage(m.text, m.rawSources || m.sources || [])
                            : "MediBot is thinking…"
                          : m.text}
                      </p>

                      {m.role === "bot" && !m.streaming && uniquePagesList.length > 0 && (
                        <div className="mt-2 pt-2 border-t border-gray-300/40 dark:border-slate-700/50 text-xs flex flex-wrap items-center text-gray-400 dark:text-gray-500">
                          {uniquePagesList.map((src, idx) => (
                            <span key={src.id || idx} className="inline-flex items-center">
                              <button
                                onClick={() => openSourcePdf(src)}
                                className="text-blue-600 dark:text-cyan-400 hover:underline font-medium focus:outline-none"
                                disabled={pdfLoading[sourceCacheKey(src)]}
                              >
                                {pdfLoading[sourceCacheKey(src)] ? `Loading Page ${src.page}...` : `Page ${src.page}`}
                              </button>
                              {idx < uniquePagesList.length - 1 && <span className="mr-1.5">,</span>}
                            </span>
                          ))}
                        </div>
                      )}


                    </div>
                  </div>
                );
              })}
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
