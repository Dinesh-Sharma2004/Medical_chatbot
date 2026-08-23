// pdfExport.js — Renders the full chat as a printable PDF document

export function exportChatToPdf(chat) {
  if (!chat || !chat.messages || chat.messages.length === 0) {
    alert("No messages to export.");
    return;
  }

  // ── Format timestamp ──────────────────────────────────────────
  const fmtDate = (ts) =>
    new Date(ts || Date.now()).toLocaleString("en-US", {
      dateStyle: "medium",
      timeStyle: "short",
    });

  const chatDate = fmtDate(chat.updatedAt || chat.createdAt);
  const modeLabel = chat.mode === "optimized" ? "Optimized RAG" : "Basic RAG";
  const modeBg    = chat.mode === "optimized" ? "#f3e8ff" : "#e0f2fe";
  const modeColor = chat.mode === "optimized" ? "#7c3aed"  : "#0369a1";

  // ── Build message HTML ────────────────────────────────────────
  const messagesHtml = chat.messages
    .map((m) => {
      const isUser = m.role === "user";
      const isBot  = m.role === "bot" || m.role === "assistant";

      // Correct field: ChatPage stores content in m.content
      const rawText = m.content || m.text || "";

      // Strip internal reasoning blocks + citation markers
      const displayText = rawText
        .replace(/<think>[\s\S]*?<\/think>/g, "")
        .replace(/<think>[\s\S]*/g, "")
        .replace(/\s*\[Evidence\s*\d+(?:\s*,\s*\d+)*\]/gi, "")
        .replace(/\s*\[p\.?\s*\d+(?:\s*,\s*\d+)*\]/gi, "")
        .trim();

      // Skip empty bot placeholders
      if (!displayText && isBot) return "";

      const roleLabel   = isUser ? "You" : "MediBot AI";
      const roleEmoji   = isUser ? "\uD83D\uDC64" : "\uD83E\uDD16";
      const headerColor = isUser ? "#0369a1" : "#7c3aed";
      const borderColor = isUser ? "#0891b2" : "#9333ea";
      const bgColor     = isUser ? "#f0f9ff" : "#faf5ff";
      const ts = m.timestamp ? fmtDate(m.timestamp) : "";

      // Citations / sources
      let citationsHtml = "";
      if (isBot && Array.isArray(m.sources) && m.sources.length > 0) {
        const seen = new Set();
        const unique = m.sources.filter((src) => {
          const pg  = src.page || src.pageLabel || src.page_label;
          const did = src.docId || src.doc_id;
          const key = `${did}:${pg}`;
          if (pg && did && !seen.has(key)) { seen.add(key); return true; }
          return false;
        });

        if (unique.length > 0) {
          const pills = unique
            .map((src) => {
              const pg   = src.pageLabel || src.page_label || src.page;
              const file = src.filename || "Uploaded PDF";
              return `<span style="display:inline-block;margin:2px 4px 2px 0;padding:2px 8px;` +
                     `background:#ede9fe;color:#6d28d9;border-radius:12px;font-size:10px;font-weight:600;">` +
                     `\uD83D\uDCC4 p.${pg} \u2014 ${file}</span>`;
            })
            .join("");
          citationsHtml =
            `<div style="margin-top:12px;padding-top:10px;border-top:1px dashed #d8b4fe;">` +
            `<div style="font-size:10px;font-weight:700;color:#7c3aed;margin-bottom:5px;` +
            `text-transform:uppercase;letter-spacing:0.5px;">Sources</div>` +
            `<div>${pills}</div></div>`;
        }
      }

      return (
        `<div style="margin-bottom:22px;padding:16px 18px;border-radius:10px;` +
        `background-color:${bgColor};border-left:4px solid ${borderColor};` +
        `page-break-inside:avoid;box-shadow:0 1px 3px rgba(0,0,0,0.06);">` +
          `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">` +
            `<span style="font-weight:800;font-size:11px;color:${headerColor};` +
            `text-transform:uppercase;letter-spacing:0.6px;">${roleEmoji} ${roleLabel}</span>` +
            (ts ? `<span style="font-size:10px;color:#94a3b8;">${ts}</span>` : "") +
          `</div>` +
          `<div style="font-size:13.5px;line-height:1.75;color:#1e293b;white-space:pre-wrap;word-wrap:break-word;">` +
            displayText +
          `</div>` +
          citationsHtml +
        `</div>`
      );
    })
    .join("");

  // ── Full report HTML ──────────────────────────────────────────
  const fullHtml =
    `<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;` +
    `padding:40px 48px;color:#1e293b;max-width:820px;margin:0 auto;">` +

    // Header
    `<div style="display:flex;justify-content:space-between;align-items:flex-start;` +
    `border-bottom:3px solid #0891b2;padding-bottom:18px;margin-bottom:28px;">` +
      `<div>` +
        `<div style="font-size:26px;font-weight:900;color:#0891b2;letter-spacing:-0.5px;">\uD83C\uDFE5 MediBot AI</div>` +
        `<div style="font-size:12px;color:#64748b;margin-top:3px;font-weight:500;">Advanced Medical RAG Consultation Summary</div>` +
      `</div>` +
      `<div style="text-align:right;font-size:11px;color:#64748b;line-height:1.9;">` +
        `<div><strong style="color:#374151;">Date:</strong> ${chatDate}</div>` +
        `<div><strong style="color:#374151;">Mode:</strong> ` +
          `<span style="background:${modeBg};color:${modeColor};padding:1px 8px;border-radius:10px;` +
          `font-weight:700;font-size:10px;">${modeLabel}</span></div>` +
        `<div><strong style="color:#374151;">Messages:</strong> ${chat.messages.length}</div>` +
      `</div>` +
    `</div>` +

    // Title block
    `<div style="margin-bottom:28px;">` +
      `<div style="font-size:20px;font-weight:800;color:#0f172a;margin-bottom:4px;">` +
        (chat.title || "Medical Consultation") +
      `</div>` +
      `<div style="font-size:10px;color:#94a3b8;">Chat ID: ${chat.chatId}</div>` +
    `</div>` +

    // Section label
    `<div style="font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;` +
    `letter-spacing:1px;margin-bottom:16px;padding-bottom:8px;border-bottom:1px solid #e2e8f0;">` +
      `Conversation Transcript` +
    `</div>` +

    // Messages
    `<div>${messagesHtml}</div>` +

    // Footer
    `<div style="margin-top:48px;padding-top:16px;border-top:1px solid #e2e8f0;` +
    `text-align:center;font-size:10px;color:#94a3b8;line-height:1.6;">` +
      `<div>Generated by <strong>MediBot AI</strong> on ${chatDate}</div>` +
      `<div style="margin-top:3px;">For clinical review and educational purposes only. Not a substitute for professional medical advice.</div>` +
    `</div>` +

    `</div>`;

  // ── Inject into DOM and print ─────────────────────────────────
  const printRoot = document.createElement("div");
  printRoot.id = "medibot-print-root";
  printRoot.innerHTML = fullHtml;
  document.body.appendChild(printRoot);

  const styleEl = document.createElement("style");
  styleEl.id = "medibot-print-style";
  styleEl.innerHTML = `
    @page {
      size: A4;
      margin: 18mm 14mm;
    }
    @media print {
      /* Hide everything except our print container */
      body > *:not(#medibot-print-root) { display: none !important; }

      body {
        background: white !important;
        margin: 0 !important;
        padding: 0 !important;
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
      }

      #medibot-print-root {
        display: block !important;
        position: static !important;   /* ← was fixed, which forced 1-page clipping */
        width: 100% !important;
        background: white !important;
        overflow: visible !important;
      }

      /* Allow individual message cards to break across pages cleanly */
      #medibot-print-root [style*="page-break-inside"] {
        page-break-inside: avoid;
      }

      /* Avoid orphaned headers at bottom of pages */
      h1, h2, h3, h4 {
        page-break-after: avoid;
      }
    }
    @media screen {
      #medibot-print-root { display: none; }
    }
  `;
  document.head.appendChild(styleEl);

  setTimeout(() => {
    window.print();
    if (document.body.contains(printRoot))  document.body.removeChild(printRoot);
    if (document.head.contains(styleEl))    document.head.removeChild(styleEl);
  }, 200);
}

