import { useState, useEffect, useCallback } from "react";
import { chatStorage } from "../services/chatStorage";

export function useChatHistory(userId, initialMode = "basic") {
  const [chats, setChats] = useState([]);
  const [activeChatId, setActiveChatId] = useState(null);

  const refreshChats = useCallback(() => {
    setChats(chatStorage.getChats(userId));
  }, [userId]);

  // Load chat list whenever user changes
  useEffect(() => {
    refreshChats();
  }, [userId, refreshChats]);

  const selectChat = useCallback((chatId) => {
    setActiveChatId(chatId);
  }, []);

  const createNewChat = useCallback((mode = initialMode) => {
    const newId = "chat-" + Date.now() + "-" + Math.random().toString(36).substring(2, 11);
    setActiveChatId(newId);
    return newId;
  }, [initialMode]);

  const saveChat = useCallback((chatId, messages, mode) => {
    if (!chatId) return;
    chatStorage.saveChat(userId, chatId, messages, mode);
    refreshChats();
  }, [userId, refreshChats]);

  const deleteChat = useCallback((chatId) => {
    chatStorage.deleteChat(userId, chatId);
    refreshChats();
    if (activeChatId === chatId) {
      setActiveChatId(null);
    }
  }, [userId, activeChatId, refreshChats]);

  const renameChat = useCallback((chatId, newTitle) => {
    chatStorage.renameChat(userId, chatId, newTitle);
    refreshChats();
  }, [userId, refreshChats]);

  const clearAllChats = useCallback(() => {
    chatStorage.clearAllChats(userId);
    setChats([]);
    setActiveChatId(null);
  }, [userId]);

  const activeChat = chats.find((c) => c.chatId === activeChatId) || null;

  return {
    chats,
    activeChatId,
    activeChat,
    selectChat,
    createNewChat,
    saveChat,
    deleteChat,
    renameChat,
    clearAllChats,
  };
}
