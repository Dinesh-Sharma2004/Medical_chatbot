import React, { useEffect, useState, useRef, useCallback } from "react";
import { health, fetchSourcePdf } from "../api";
import { pushToast } from "../components/ToastContainer";
import ChatInput from "../components/ChatInput";
import EmptyState from "../components/EmptyState";
import ChatHistorySidebar from "../components/ChatHistorySidebar";
import { useChatHistory } from "../hooks/useChatHistory";
import { useAskStream } from "../hooks/useAskStream";
import { chatStorage } from "../services/chatStorage";
import { exportChatToPdf } from "../services/pdfExport";
import { Sparkles, Database, ExternalLink, ArrowDown, Info } from "lucide-react";

export default function ChatPage({ token, user }) {
  const getUserId = () => user?.id || user?.email || "anonymous";
  const userId = getUserId();

  const [initialMode, setInitialMode] = useState("basic");
  const {
    chats,
    activeChatId,
    activeChat,
    selectChat,
    createNewChat,
    saveChat,
    deleteChat,
    renameChat,
    clearAllChats,
  } = useChatHistory(userId, "basic");

  const currentMode = activeChat ? activeChat.mode : initialMode;
  // MUST be declared before `messages` which reads it (avoids TDZ crash)
  const [streamingMessages, setStreamingMessages] = useState(null);
  const streamingMessagesRef = useRef(null);
  // Use streamingMessages when actively streaming, else use persisted messages
  const messages = streamingMessages ?? (activeChat ? activeChat.messages : []);

  const { ask, isLoading, cancel } = useAskStream(token);
  const [pdfLoading, setPdfLoading] = useState({});
  const [input, setInput] = useState("");

  // Request isolation states
  const [activeRequestId, setActiveRequestId] = useState(null);
  const [activeMessageId, setActiveMessageId] = useState(null);

  const activeRequestIdRef = useRef(null);
  useEffect(() => {
    activeRequestIdRef.current = activeRequestId;
  }, [activeRequestId]);

  useEffect(() => {
    streamingMessagesRef.current = streamingMessages;
  }, [streamingMessages]);
  // Keep a ref to reqId that is set synchronously (avoids async setState gap)
  const currentReqIdRef = useRef(null);

  const chatRef = useRef(null);
  const scrollLockRef = useRef(false);
  const [showScrollButton, setShowScrollButton] = useState(false);

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

  useEffect(() => {
    const el = chatRef.current;
    if (!el) return;
    const observer = new MutationObserver(() => {
      if (!scrollLockRef.current) scrollToBottom(true);
    });
    observer.observe(el, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [scrollToBottom]);

  // Clean up streaming on unmount
  useEffect(() => {
    return () => {
      cancel();
    };
  }, [cancel]);

  // Helpers for citations formatting
  function sourceCacheKey(source = {}) {
    return `${source.pageKey || source.docId || source.filename || "source"}:${source.page || "?"}`;
  }

  function cleanReasoning(text = "") {
    let clean = text.replace(/<think>[\s\S]*?<\/think>/g, "");
    const thinkIdx = clean.indexOf("<think>");
    if (thinkIdx >= 0) {
      clean = clean.substring(0, thinkIdx);
    }
    return clean;
  }

  function renderFormattedMessage(text) {
    if (!text) return null;
    let cleanText = cleanReasoning(text);
    cleanText = cleanText.replace(/\s*\[Evidence\s*\d+(?:\s*,\s*\d+)*\]/gi, "");
    cleanText = cleanText.replace(/\s*\[p\.?\s*\d+(?:\s*,\s*\d+)*\]/gi, "");
    cleanText = cleanText.replace(/\s*\[Evidence\s+[^\]]+\]/gi, "");
    cleanText = cleanText.replace(/\s*\[p\.?\s+[^\]]+\]/gi, "");
    return cleanText;
  }

  function normalizeRawSources(items = []) {
    return (items || []).map((s, index) => {
      const page = Number(s.page || s.page_number || s.page_label || s.pageLabel || s.p || s.raw_page || 0) || 0;
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
        const page = Number(s.page || s.page_number || s.page_label || s.pageLabel || s.p || s.raw_page || 0) || 0;
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

  // === 🔹 Send Message ===
  const sendMessage = async () => {
    const question = input.trim();
    if (!question) return;

    const reqId = "req-" + Date.now() + "-" + Math.random().toString(36).substring(2, 11);
    const userMsgId = "msg-" + Date.now() + "-user";
    const botMsgId  = "msg-" + Date.now() + "-bot";

    const userMsg = {
      messageId: userMsgId,
      role: "user",
      content: question,
      timestamp: Date.now()
    };

    const botMsg = {
      messageId: botMsgId,
      role: "bot",
      content: "",
      streaming: true,
      requestId: reqId,
      status: "pending",
      timestamp: Date.now(),
      sources: []
    };

    let targetChatId = activeChatId;
    if (!targetChatId) {
      targetChatId = createNewChat(currentMode);
    }

    const baseMessages = activeChat ? activeChat.messages : [];
    const initialMessages = [...baseMessages, userMsg, botMsg];

    // Set synchronously so the ref guard works before any async gap
    currentReqIdRef.current = reqId;
    activeRequestIdRef.current = reqId;

    setActiveRequestId(reqId);
    setActiveMessageId(botMsgId);
    streamingMessagesRef.current = initialMessages;
    setStreamingMessages(initialMessages);  // show user msg + thinking placeholder immediately
    setInput("");

    // Persist initial state (user msg + empty bot placeholder)
    saveChat(targetChatId, initialMessages, currentMode);

    try {
      await ask(question, currentMode, {
        requestId: reqId,
        onChunk: (text, rawSources) => {
          // Guard: ignore if a newer request has started
          if (currentReqIdRef.current !== reqId) return;

          setStreamingMessages(prev => {
            if (!prev) return prev;
            const nextMessages = prev.map(m =>
              m.messageId === botMsgId
                ? { ...m, content: text, status: "streaming", sources: normalizeSources(rawSources) }
                : m
            );
            streamingMessagesRef.current = nextMessages;
            return nextMessages;
          });
        },

        onDone: (text, rawSources) => {
          if (currentReqIdRef.current !== reqId) return;

          const latestMessages = streamingMessagesRef.current ?? initialMessages;
          const streamedBotMessage = latestMessages.find((m) => m.messageId === botMsgId);
          const finalText = text.trim() || streamedBotMessage?.content?.trim() || "";

          const finalMsgs = latestMessages.map(m =>
            m.messageId === botMsgId
              ? {
                  ...m,
                  content: finalText,
                  streaming: false,
                  status: "completed",
                  sources: normalizeSources(rawSources),
                  rawSources: normalizeRawSources(rawSources)
                }
              : m
          );

          // Persist completed conversation to localStorage
          saveChat(targetChatId, finalMsgs, currentMode);
          streamingMessagesRef.current = null;
          setStreamingMessages(null);  // hand back control to persisted state
          currentReqIdRef.current = null;
          setActiveRequestId(null);
          setActiveMessageId(null);
          setTimeout(() => scrollToBottom(false), 100);
        },

        onError: (errText, isTimeout = false) => {
          if (currentReqIdRef.current !== reqId) return;

          const latestMessages = streamingMessagesRef.current ?? initialMessages;
          const errMsgs = latestMessages.map(m =>
            m.messageId === botMsgId
              ? { ...m, content: errText, streaming: false, status: isTimeout ? "timed_out" : "failed", sources: [] }
              : m
          );

          saveChat(targetChatId, errMsgs, currentMode);
          streamingMessagesRef.current = null;
          setStreamingMessages(null);
          currentReqIdRef.current = null;
          setActiveRequestId(null);
          setActiveMessageId(null);
        }
      });
    } catch (err) {
      if (currentReqIdRef.current === reqId) {
        currentReqIdRef.current = null;
        setStreamingMessages(null);
        setActiveRequestId(null);
        setActiveMessageId(null);
      }
    }
  };

  const handleCancel = () => {
    cancel();
    currentReqIdRef.current = null;
    // Remove the in-progress bot message from streaming state, then persist
    if (activeChatId && activeMessageId) {
      const clearedMsgs = (streamingMessagesRef.current ?? []).filter(m => m.messageId !== activeMessageId);
      if (clearedMsgs.length > 0) saveChat(activeChatId, clearedMsgs, currentMode);
    }
    streamingMessagesRef.current = null;
    setStreamingMessages(null);
    setActiveRequestId(null);
    setActiveMessageId(null);
  };

  const handleNewChat = () => {
    if (activeRequestId) {
      handleCancel();
    }
    createNewChat(currentMode);
  };

  const handleSelectChat = (chatId) => {
    if (activeRequestId) {
      handleCancel();
    }
    selectChat(chatId);
  };

  const handleModeChange = (newMode) => {
    if (activeChatId && activeChat) {
      saveChat(activeChatId, messages, newMode);
    } else {
      setInitialMode(newMode);
    }
  };

  const handleExportPdf = () => {
    if (activeChat) {
      exportChatToPdf(activeChat);
    }
  };

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
    <div className="w-full max-w-[95%] mx-auto h-[calc(100vh-130px)] flex flex-col">
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6 flex-1 min-h-0">
        
        {/* Chat History Sidebar */}
        <ChatHistorySidebar
          chats={chats}
          activeChatId={activeChatId}
          onSelectChat={handleSelectChat}
          onNewChat={handleNewChat}
          onDeleteChat={deleteChat}
          onRenameChat={renameChat}
          onClearAll={clearAllChats}
        />

        {/* Chat Column */}
        <div className="lg:col-span-4 flex flex-col h-full min-h-0 relative">
          <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border-2 
                          border-gray-200 dark:border-cyan-500/20 flex flex-col flex-1 min-h-0">

            {/* Header */}
            <div
              className={`bg-gradient-to-r ${
                currentMode === "basic"
                  ? "from-blue-600 to-cyan-600"
                  : "from-purple-600 to-pink-600"
              } p-4 flex items-center justify-between rounded-t-2xl`}
            >
              <div className="flex items-center gap-3">
                <div className="p-2 bg-white/20 rounded-xl backdrop-blur-sm shadow-md">
                  {currentMode === "basic" ? (
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
                    {currentMode === "basic" ? "Basic RAG" : "Optimized RAG"} •{" "}
                    {messages.length} messages
                  </p>
                </div>
              </div>

              {activeChat && messages.length > 0 && (
                <button
                  onClick={handleExportPdf}
                  className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-white/10 hover:bg-white/25
                             text-white font-bold text-xs transition-all duration-300 hover:scale-105 active:scale-98 shadow-md"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  Export PDF
                </button>
              )}
            </div>

            {/* RAG Mode Switcher */}
            <div className="flex justify-center gap-4 p-3 bg-gray-50 dark:bg-slate-900/50 border-b border-gray-200 dark:border-cyan-500/20">

              {/* ── Basic RAG ── */}
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => handleModeChange("basic")}
                  className={`flex items-center gap-2 px-5 py-2.5 rounded-xl border-2 text-sm font-bold transition-all duration-300 hover:scale-[1.03] active:scale-98 ${
                    currentMode === "basic"
                      ? "bg-gradient-to-r from-blue-500 via-cyan-500 to-blue-600 text-white border-transparent shadow-lg shadow-cyan-500/20 scale-105"
                      : "bg-white dark:bg-slate-800 text-gray-700 dark:text-gray-300 border-gray-200 dark:border-gray-700/60 hover:border-cyan-500/60"
                  }`}
                >
                  <Database className="w-4 h-4" />
                  Basic RAG
                </button>

                {/* Info icon + tooltip for Basic RAG */}
                <div className="relative group">
                  <button
                    type="button"
                    className="p-1 rounded-full text-blue-400 hover:text-blue-600 dark:text-blue-400 dark:hover:text-blue-300
                               hover:bg-blue-50 dark:hover:bg-blue-900/30 transition-all duration-200 focus:outline-none"
                    tabIndex={0}
                    aria-label="Basic RAG info"
                  >
                    <Info className="w-4 h-4" />
                  </button>
                  {/* Tooltip */}
                  <div className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50
                                  opacity-0 group-hover:opacity-100 translate-y-1 group-hover:translate-y-0
                                  transition-all duration-200 w-64">
                    <div className="bg-slate-900 dark:bg-slate-800 text-white text-xs rounded-xl shadow-2xl
                                    border border-blue-500/30 p-3.5 text-left">
                      <div className="flex items-center gap-1.5 mb-2">
                        <Database className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
                        <span className="font-bold text-cyan-300">Basic RAG</span>
                      </div>
                      <ul className="space-y-1.5 text-gray-300 leading-snug">
                        <li className="flex items-start gap-1.5"><span className="text-cyan-400 mt-0.5">▸</span>Direct similarity search over the vector store</li>
                        <li className="flex items-start gap-1.5"><span className="text-cyan-400 mt-0.5">▸</span>Retrieves the top-k most relevant document chunks</li>
                        <li className="flex items-start gap-1.5"><span className="text-cyan-400 mt-0.5">▸</span>Fast &amp; lightweight — best for straightforward factual queries</li>
                        <li className="flex items-start gap-1.5"><span className="text-cyan-400 mt-0.5">▸</span>Lower inference cost and latency</li>
                      </ul>
                    </div>
                    {/* Arrow */}
                    <div className="w-3 h-3 bg-slate-900 dark:bg-slate-800 border-b border-r border-blue-500/30
                                    rotate-45 mx-auto -mt-1.5"></div>
                  </div>
                </div>
              </div>

              {/* ── Optimized RAG ── */}
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => handleModeChange("optimized")}
                  className={`flex items-center gap-2 px-5 py-2.5 rounded-xl border-2 text-sm font-bold transition-all duration-300 hover:scale-[1.03] active:scale-98 ${
                    currentMode === "optimized"
                      ? "bg-gradient-to-r from-purple-500 via-pink-500 to-purple-600 text-white border-transparent shadow-lg shadow-purple-500/20 scale-105"
                      : "bg-white dark:bg-slate-800 text-gray-700 dark:text-gray-300 border-gray-200 dark:border-gray-700/60 hover:border-purple-500/60"
                  }`}
                >
                  <Sparkles className="w-4 h-4" />
                  Optimized RAG
                </button>

                {/* Info icon + tooltip for Optimized RAG */}
                <div className="relative group">
                  <button
                    type="button"
                    className="p-1 rounded-full text-purple-400 hover:text-purple-600 dark:text-purple-400 dark:hover:text-purple-300
                               hover:bg-purple-50 dark:hover:bg-purple-900/30 transition-all duration-200 focus:outline-none"
                    tabIndex={0}
                    aria-label="Optimized RAG info"
                  >
                    <Info className="w-4 h-4" />
                  </button>
                  {/* Tooltip */}
                  <div className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50
                                  opacity-0 group-hover:opacity-100 translate-y-1 group-hover:translate-y-0
                                  transition-all duration-200 w-72">
                    <div className="bg-slate-900 dark:bg-slate-800 text-white text-xs rounded-xl shadow-2xl
                                    border border-purple-500/30 p-3.5 text-left">
                      <div className="flex items-center gap-1.5 mb-2">
                        <Sparkles className="w-3.5 h-3.5 text-purple-400 shrink-0" />
                        <span className="font-bold text-purple-300">Optimized RAG</span>
                      </div>
                      <ul className="space-y-1.5 text-gray-300 leading-snug">
                        <li className="flex items-start gap-1.5"><span className="text-purple-400 mt-0.5">▸</span>Multi-stage retrieval with re-ranking and query expansion</li>
                        <li className="flex items-start gap-1.5"><span className="text-purple-400 mt-0.5">▸</span>Filters low-relevance chunks before sending to the LLM</li>
                        <li className="flex items-start gap-1.5"><span className="text-purple-400 mt-0.5">▸</span>Higher answer accuracy on complex medical questions</li>
                        <li className="flex items-start gap-1.5"><span className="text-purple-400 mt-0.5">▸</span>Slightly higher inference cost — best for critical queries</li>
                      </ul>
                    </div>
                    {/* Arrow */}
                    <div className="w-3 h-3 bg-slate-900 dark:bg-slate-800 border-b border-r border-purple-500/30
                                    rotate-45 mx-auto -mt-1.5"></div>
                  </div>
                </div>
              </div>

            </div>

            {/* Chat Messages */}
            <div
              ref={chatRef}
              className="flex-1 overflow-y-auto overflow-x-hidden p-5 space-y-5 
                         bg-gradient-to-b from-gray-50/60 to-white dark:from-slate-950/60 dark:to-slate-900"
            >
              {messages.length === 0 && <EmptyState />}

              {messages.map((m) => {
                const uniquePagesList = [];
                if (m.role === "bot" || m.role === "assistant") {
                  if (Array.isArray(m.sources)) {
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
                }

                const isBot = m.role === "bot" || m.role === "assistant";

                return (
                  <div key={m.messageId} className="flex flex-col">
                    <div
                      className={`max-w-[85%] md:max-w-[75%] rounded-2xl px-4 py-3 shadow-sm 
                        ${
                          !isBot
                            ? "ml-auto bg-gradient-to-r from-cyan-500 to-blue-600 text-white"
                            : "mr-auto bg-gray-100 dark:bg-slate-800 text-gray-800 dark:text-gray-100"
                        } ${m.streaming ? "streaming-placeholder" : ""}`}
                    >
                      <p className="whitespace-pre-line text-[15px] leading-relaxed">
                        {isBot ? (
                          (() => {
                            const display = renderFormattedMessage(m.content);
                            if (display) return display;
                            if (m.streaming) return (
                              <span className="flex items-center gap-1.5 text-gray-400 dark:text-gray-500 italic text-sm">
                                <span className="inline-flex gap-0.5">
                                  <span className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                                  <span className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                                  <span className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                                </span>
                                MediBot is thinking…
                              </span>
                            );
                            return "I couldn't generate an answer right now. Please try again.";
                          })()
                        ) : m.content}
                      </p>

                      {isBot && !m.streaming && uniquePagesList.length > 0 && (
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
                onCancel={handleCancel}
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
