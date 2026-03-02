import { useState, useCallback, useRef } from "react";
import { ENDPOINTS } from "../api";

export function useAskStream() {
  const [isLoading, setIsLoading] = useState(false);
  const [answer, setAnswer] = useState("");
  const [sources, setSources] = useState([]);
  const controllerRef = useRef(null);

  const ask = useCallback(async (question, mode = "basic") => {
    setIsLoading(true);
    // Don't clear previous answer here (avoids hiding previous messages)
    setSources([]);

    if (controllerRef.current) {
      try { controllerRef.current.abort(); } catch {}
    }

    const controller = new AbortController();
    controllerRef.current = controller;

    try {
      const response = await fetch(ENDPOINTS.ASK_STREAM, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, mode }),
        signal: controller.signal,
      });

      if (!response.ok) {
        const errText = await response.text().catch(() => "Stream failed");
        setAnswer(`Error: ${errText}`);
        setIsLoading(false);
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let accumulated = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();

        for (let line of lines) {
          if (!line.trim()) continue;
          let obj;
          try {
            obj = JSON.parse(line);
          } catch {
            continue;
          }

          if (obj.type === "sources") {
            setSources(obj.sources || []);
            continue;
          }

          if (obj.type === "partial") {
            const chunk = obj.text || "";
            if (chunk && !accumulated.endsWith(chunk)) {
              accumulated += chunk;
              setAnswer(accumulated);
            }
            continue;
          }

          if (obj.type === "done") {
            const finalText = obj.text?.trim() || accumulated;
            setAnswer(finalText);
            setSources(obj.sources || sources);
            setIsLoading(false);
            controllerRef.current = null;
            return;
          }

          if (obj.type === "error") {
            setAnswer("Error: " + obj.message);
            setIsLoading(false);
            controllerRef.current = null;
            return;
          }
        }
      }

      setIsLoading(false);
    } catch (err) {
      if (err.name === "AbortError") {
        setAnswer((p) => p + "\n[Stream cancelled]");
      } else {
        setAnswer((p) => p + `\n[Error: ${err.message}]`);
      }
      setIsLoading(false);
    } finally {
      controllerRef.current = null;
    }
  }, [sources]);

  const cancel = useCallback(() => {
    if (controllerRef.current) {
      controllerRef.current.abort();
      controllerRef.current = null;
      setIsLoading(false);
    }
  }, []);

  return { ask, isLoading, answer, sources, cancel, setAnswer };
}
