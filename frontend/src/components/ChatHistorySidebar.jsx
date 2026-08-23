// ChatHistorySidebar.jsx
import React, { useState, useRef, useEffect } from "react";
import { Plus, MessageSquare, Trash2, Calendar, Pencil, Check, X } from "lucide-react";
import { groupChatsByDate } from "../services/chatStorage";

export default function ChatHistorySidebar({
  chats,
  activeChatId,
  onSelectChat,
  onNewChat,
  onDeleteChat,
  onRenameChat,
  onClearAll
}) {
  const grouped = groupChatsByDate(chats);
  const [editingId, setEditingId]   = useState(null);
  const [editingVal, setEditingVal] = useState("");
  const inputRef = useRef(null);

  // Focus the input whenever edit mode starts
  useEffect(() => {
    if (editingId && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editingId]);

  function startRename(e, chat) {
    e.stopPropagation();
    setEditingId(chat.chatId);
    setEditingVal(chat.title || "");
  }

  function commitRename(chatId) {
    if (editingVal.trim()) {
      onRenameChat(chatId, editingVal.trim());
    }
    setEditingId(null);
    setEditingVal("");
  }

  function cancelRename() {
    setEditingId(null);
    setEditingVal("");
  }

  const renderGroup = (label, items) => {
    if (items.length === 0) return null;

    return (
      <div className="space-y-1">
        <h4 className="text-xs font-semibold text-cyan-600/80 dark:text-cyan-400/80 uppercase tracking-wider px-3 py-2 flex items-center gap-1.5">
          <Calendar className="w-3 h-3" />
          {label}
        </h4>
        {items.map((chat) => {
          const isActive  = chat.chatId === activeChatId;
          const isEditing = editingId === chat.chatId;

          return (
            <div
              key={chat.chatId}
              className={`group flex items-center justify-between rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-200 cursor-pointer
                ${isActive
                  ? "bg-gradient-to-r from-cyan-500/10 to-blue-500/10 border-l-4 border-cyan-500 text-gray-900 dark:text-white shadow-sm"
                  : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-slate-800/60"
                }`}
              onClick={() => !isEditing && onSelectChat(chat.chatId)}
            >
              {/* Icon */}
              <MessageSquare className={`w-4 h-4 shrink-0 mr-2 ${isActive ? "text-cyan-500" : "text-gray-400"}`} />

              {/* Title or inline edit input */}
              {isEditing ? (
                <input
                  ref={inputRef}
                  value={editingVal}
                  onChange={(e) => setEditingVal(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter")  { e.preventDefault(); commitRename(chat.chatId); }
                    if (e.key === "Escape") { e.preventDefault(); cancelRename(); }
                  }}
                  onClick={(e) => e.stopPropagation()}
                  className="flex-1 min-w-0 bg-white dark:bg-slate-700 border border-cyan-400 dark:border-cyan-500
                             rounded-lg px-2 py-0.5 text-sm text-gray-900 dark:text-white outline-none
                             focus:ring-2 focus:ring-cyan-400/50 transition-all"
                  maxLength={60}
                />
              ) : (
                <span
                  className="flex-1 min-w-0 truncate pr-1 text-[13.5px]"
                  onDoubleClick={(e) => startRename(e, chat)}
                  title="Double-click to rename"
                >
                  {chat.title || "New Chat"}
                </span>
              )}

              {/* Action buttons */}
              <div className={`flex items-center gap-0.5 shrink-0 ml-1 ${isEditing ? "flex" : "opacity-0 group-hover:opacity-100"} transition-opacity duration-150`}>
                {isEditing ? (
                  <>
                    {/* Confirm rename */}
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); commitRename(chat.chatId); }}
                      className="p-1 rounded-md hover:bg-green-100 dark:hover:bg-green-900/30 text-green-600 dark:text-green-400 transition-colors"
                      title="Save"
                    >
                      <Check className="w-3.5 h-3.5" />
                    </button>
                    {/* Cancel rename */}
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); cancelRename(); }}
                      className="p-1 rounded-md hover:bg-gray-100 dark:hover:bg-slate-700 text-gray-500 dark:text-gray-400 transition-colors"
                      title="Cancel"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </>
                ) : (
                  <>
                    {/* Rename button */}
                    <button
                      type="button"
                      onClick={(e) => startRename(e, chat)}
                      className="p-1 rounded-md hover:bg-blue-50 dark:hover:bg-blue-900/20 text-gray-400 hover:text-blue-500 dark:hover:text-blue-400 transition-colors"
                      title="Rename conversation"
                    >
                      <Pencil className="w-3.5 h-3.5" />
                    </button>
                    {/* Delete button */}
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); onDeleteChat(chat.chatId); }}
                      className="p-1 rounded-md hover:bg-red-50 dark:hover:bg-red-900/20 text-gray-400 hover:text-red-500 dark:hover:text-red-400 transition-colors"
                      title="Delete conversation"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div className="lg:col-span-1 flex flex-col h-full bg-white dark:bg-slate-900 rounded-2xl shadow-xl border-2 border-gray-200 dark:border-cyan-500/20 p-4 min-h-0">

      {/* New Chat Button */}
      <button
        onClick={onNewChat}
        className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl
                 bg-gradient-to-r from-cyan-500 via-blue-500 to-indigo-600 text-white font-bold text-sm
                 hover:shadow-2xl hover:shadow-cyan-500/30 hover:scale-105 active:scale-98
                 transition-all duration-300 mb-6 border border-white/10"
      >
        <Plus className="w-5 h-5" />
        New Chat
      </button>

      {/* Conversations Scroll List */}
      <div className="flex-1 overflow-y-auto space-y-4 pr-1 scrollbar-thin scrollbar-thumb-gray-200 dark:scrollbar-thumb-slate-800">
        {chats.length === 0 ? (
          <div className="text-center py-8 text-gray-400 dark:text-gray-500 text-xs font-medium">
            No previous conversations.
          </div>
        ) : (
          <>
            {renderGroup("Today", grouped.today)}
            {renderGroup("Yesterday", grouped.yesterday)}
            {renderGroup("Older", grouped.older)}
          </>
        )}
      </div>

      {/* Clear All Footer */}
      {chats.length > 0 && (
        <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-800 shrink-0">
          <button
            onClick={onClearAll}
            className="w-full flex items-center justify-center gap-2 px-3 py-2.5 text-xs font-bold
                     rounded-xl bg-red-50 dark:bg-red-950/20 text-red-600 dark:text-red-400
                     border border-red-200/60 dark:border-red-900/40
                     hover:bg-red-100 dark:hover:bg-red-900/40 hover:scale-105 active:scale-98
                     transition-all duration-300"
          >
            <Trash2 className="w-3.5 h-3.5" />
            Clear All History
          </button>
        </div>
      )}
    </div>
  );
}

