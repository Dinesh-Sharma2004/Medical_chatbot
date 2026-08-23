// frontend/src/services/chatStorage.js

const getStorageKey = (userId) => `medibot_chats_${userId || "guest"}`;

export const chatStorage = {
  getChats(userId) {
    try {
      const data = localStorage.getItem(getStorageKey(userId));
      return data ? JSON.parse(data) : [];
    } catch (e) {
      console.error("Failed to load chats from localStorage", e);
      return [];
    }
  },

  saveChats(userId, chats) {
    try {
      localStorage.setItem(getStorageKey(userId), JSON.stringify(chats));
    } catch (e) {
      console.error("Failed to save chats to localStorage", e);
    }
  },

  getChat(userId, chatId) {
    const chats = this.getChats(userId);
    return chats.find((c) => c.chatId === chatId) || null;
  },

  saveChat(userId, chatId, messages, mode) {
    const chats = this.getChats(userId);
    let chat = chats.find((c) => c.chatId === chatId);
    const now = Date.now();

    if (!chat) {
      // Create new chat entry
      const firstUserMsg = messages.find((m) => m.role === "user");
      let title = "New Chat";
      if (firstUserMsg && firstUserMsg.text) {
        title = generateShortTitle(firstUserMsg.text);
      }

      chat = {
        chatId,
        title,
        createdAt: now,
        updatedAt: now,
        mode: mode || "basic",
        messages,
      };
      chats.unshift(chat); // Put new chat at the top
    } else {
      // Update existing chat
      if (chat.title === "New Chat" || !chat.title) {
        const firstUserMsg = messages.find((m) => m.role === "user");
        if (firstUserMsg && firstUserMsg.text) {
          chat.title = generateShortTitle(firstUserMsg.text);
        }
      }
      chat.messages = messages;
      chat.mode = mode || chat.mode || "basic";
      chat.updatedAt = now;

      // Move updated chat to the top
      const idx = chats.findIndex((c) => c.chatId === chatId);
      if (idx > 0) {
        chats.splice(idx, 1);
        chats.unshift(chat);
      }
    }

    this.saveChats(userId, chats);
    return chat;
  },

  deleteChat(userId, chatId) {
    const chats = this.getChats(userId);
    const filtered = chats.filter((c) => c.chatId !== chatId);
    this.saveChats(userId, filtered);
  },

  renameChat(userId, chatId, newTitle) {
    const chats = this.getChats(userId);
    const chat = chats.find((c) => c.chatId === chatId);
    if (chat && newTitle && newTitle.trim()) {
      chat.title = newTitle.trim();
      this.saveChats(userId, chats);
    }
  },

  clearAllChats(userId) {
    this.saveChats(userId, []);
  }
};

// Lightweight deterministic title generation
function generateShortTitle(text) {
  if (!text) return "New Chat";
  let clean = text.replace(/[?.,!/\\#@$%^&*()_+\-=\[\]{};':"|,.<>\/]/g, "").trim();
  const stopwords = /^(what\s+is\s+|how\s+to\s+|explain\s+|describe\s+|could\s+you\s+|tell\s+me\s+about\s+|can\s+you\s+explain\s+)/i;
  clean = clean.replace(stopwords, "");
  const words = clean.split(/\s+/).slice(0, 4);
  let title = words.join(" ");
  title = title.replace(/\b\w/g, (c) => c.toUpperCase());
  if (title.length > 30) {
    title = title.substring(0, 27) + "...";
  }
  return title || "Medical Query";
}

// Group chats by date
export function groupChatsByDate(chats = []) {
  const groups = {
    today: [],
    yesterday: [],
    older: []
  };

  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);

  const startOfYesterday = new Date(startOfToday);
  startOfYesterday.setDate(startOfYesterday.getDate() - 1);

  chats.forEach((chat) => {
    const date = new Date(chat.updatedAt || chat.createdAt);
    if (date >= startOfToday) {
      groups.today.push(chat);
    } else if (date >= startOfYesterday) {
      groups.yesterday.push(chat);
    } else {
      groups.older.push(chat);
    }
  });

  return groups;
}
