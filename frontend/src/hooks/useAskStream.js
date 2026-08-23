import { useCallback, useRef, useState } from "react";
import { askQuestion, askStream } from "../api";

const REQUEST_TIMEOUT_MS = 100_000;

function stripInvisibleModelOutput(text = "") {
  let clean = text.replace(/<think>[\s\S]*?<\/think>/g, "");
  const danglingThinkIdx = clean.indexOf("<think>");
  if (danglingThinkIdx >= 0) {
    clean = clean.substring(0, danglingThinkIdx);
  }
  return clean.trim();
}

export function useAskStream(token) {
  const [isLoading, setIsLoading] = useState(false);
  const controllerRef = useRef(null);

  const ask = useCallback(async (question, mode, { requestId, onChunk, onDone, onError }) => {
    setIsLoading(true);

    if (controllerRef.current) {
      try {
        controllerRef.current.abort();
      } catch {}
    }

    const controller = new AbortController();
    controllerRef.current = controller;

    let sources = [];
    let accumulatedText = "";

    // Leave room for the backend to load a cold embedding model and generate a response.
    const timeoutId = setTimeout(() => {
      if (controllerRef.current) {
        controllerRef.current.abort();
      }
      setIsLoading(false);
      onError("I couldn't find a reliable answer to this question in the uploaded document.", true); // true = isTimeout
    }, REQUEST_TIMEOUT_MS);

    try {
      const response = await askStream(question, mode, {
        signal: controller.signal,
        token,
        requestId,
      });

      if (!response.ok) {
        clearTimeout(timeoutId);
        const errText = await response.text().catch(() => "Stream failed");
        setIsLoading(false);
        onError(errText, false);
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

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
            sources = obj.sources || [];
            onChunk(accumulatedText, sources);
            continue;
          }

          if (obj.type === "partial") {
            const chunk = obj.text || "";
            if (chunk) {
              accumulatedText += chunk;
              onChunk(accumulatedText, sources);
            }
            continue;
          }

          if (obj.type === "done") {
            clearTimeout(timeoutId);
            const finalText = obj.text?.trim() || accumulatedText;
            let completedText = finalText;
            let completedSources = sources;

            if (!stripInvisibleModelOutput(finalText)) {
              try {
                const fallback = await askQuestion(question, mode, token);
                if (controller.signal.aborted) {
                  setIsLoading(false);
                  controllerRef.current = null;
                  return;
                }
                completedText = fallback?.answer?.trim() || finalText;
                completedSources = fallback?.sources || sources;
              } catch (fallbackErr) {
                console.warn("Non-stream fallback failed", fallbackErr);
              }
            }

            onDone(completedText, completedSources);
            setIsLoading(false);
            controllerRef.current = null;
            return;
          }

          if (obj.type === "error") {
            clearTimeout(timeoutId);
            setIsLoading(false);
            onError(obj.message, false);
            controllerRef.current = null;
            return;
          }
        }
      }

      clearTimeout(timeoutId);
      let completedText = accumulatedText;
      let completedSources = sources;

      if (!stripInvisibleModelOutput(accumulatedText)) {
        try {
          const fallback = await askQuestion(question, mode, token);
          if (controller.signal.aborted) {
            setIsLoading(false);
            controllerRef.current = null;
            return;
          }
          completedText = fallback?.answer?.trim() || accumulatedText;
          completedSources = fallback?.sources || sources;
        } catch (fallbackErr) {
          console.warn("Non-stream fallback failed", fallbackErr);
        }
      }

      onDone(completedText, completedSources);
      setIsLoading(false);
    } catch (err) {
      clearTimeout(timeoutId);
      setIsLoading(false);
      if (err.name === "AbortError") {
        // Request aborted cleanly
      } else {
        onError(err.message, false);
      }
    } finally {
      controllerRef.current = null;
    }
  }, [token]);

  const cancel = useCallback(() => {
    if (controllerRef.current) {
      controllerRef.current.abort();
      controllerRef.current = null;
      setIsLoading(false);
    }
  }, []);

  return { ask, isLoading, cancel };
}
