import React, { useState, useEffect, useRef, useCallback } from "react";
import "./ChatWindow.css";
import { streamChat, getHealth } from "../api/api";
import Message from "./Message";
import SuggestedPrompts from "./SuggestedPrompts";
import ModelPin from "./ModelPin";

const WELCOME = {
  role: "assistant",
  content:
    "Hi! I'm the **PartSelect** parts assistant. I can help you find **refrigerator and dishwasher** parts, check if a part fits your model, walk through installation, troubleshoot a symptom, or manage your cart.\n\nWhat can I help you with?",
  cards: [],
  suggestions: [],
};

// Starter chips shown on an empty conversation — the three brief from the
// case study plus a couple that exercise transactions / model lookup.
const STARTER_PROMPTS = [
  "How can I install part number PS11752778?",
  "Is part PS11752778 compatible with my 10640262010 model?",
  "The ice maker on my Whirlpool fridge is not working. How can I fix it?",
  "What parts fit my WDT780SAEM1 dishwasher?",
  "Can you tell me what parts are compatible with JDR8895AAS?",
];

function ChatWindow() {
  const [messages, setMessages] = useState([WELCOME]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [modelNumber, setModelNumber] = useState(null);
  const [health, setHealth] = useState(null);

  const scrollRef = useRef(null);
  const taRef = useRef(null);

  useEffect(() => {
    getHealth().then(setHealth);
  }, []);

  const scrollToBottom = useCallback(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  // Auto-grow the textarea up to a cap.
  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 140) + "px";
  }, [input]);

  const send = useCallback(
    async (text) => {
      const trimmed = text.trim();
      if (!trimmed || busy) return;

      const userMsg = { role: "user", content: trimmed };
      // History sent to the backend is just role/content pairs.
      const history = [
        ...messages.map((m) => ({ role: m.role, content: m.content })),
        userMsg,
      ];

      setMessages((prev) => [
        ...prev,
        userMsg,
        { role: "assistant", content: "", cards: [], suggestions: [], streaming: true },
      ]);
      setInput("");
      setBusy(true);

      const assistantIdx = messages.length + 1; // index of the placeholder

      await streamChat(history, modelNumber, {
        onToken: (tok) => {
          setMessages((prev) => {
            const next = [...prev];
            const m = next[assistantIdx];
            if (m) next[assistantIdx] = { ...m, content: m.content + tok };
            return next;
          });
        },
        onMeta: (meta) => {
          setMessages((prev) => {
            const next = [...prev];
            const m = next[assistantIdx];
            if (m)
              next[assistantIdx] = {
                ...m,
                cards: meta?.cards || [],
                suggestions: meta?.suggestions || [],
              };
            return next;
          });
        },
        onDone: () => {
          setMessages((prev) => {
            const next = [...prev];
            const m = next[assistantIdx];
            if (m) next[assistantIdx] = { ...m, streaming: false };
            return next;
          });
          setBusy(false);
        },
        onError: () => {
          setMessages((prev) => {
            const next = [...prev];
            next[assistantIdx] = {
              role: "assistant",
              content:
                "Sorry — I couldn't reach the assistant service. Please make sure the backend is running and an API key is configured, then try again.",
              cards: [],
              suggestions: [],
              streaming: false,
            };
            return next;
          });
          setBusy(false);
        },
      });
    },
    [messages, busy, modelNumber]
  );

  const onKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  };

  const reset = () => {
    setMessages([WELCOME]);
    setModelNumber(null);
    setInput("");
  };

  const showStarters = messages.length <= 1 && !busy;

  return (
    <div className="chat">
      <div className="chat-toolbar">
        <div className="status">
          <span className={`dot ${health?.api_key_configured ? "ok" : "off"}`} />
          {health ? (
            <span>
              {health.api_key_configured ? "Connected" : "No API key"} ·{" "}
              <span className="muted">
                {health.provider}/{health.model}
              </span>
            </span>
          ) : (
            <span className="muted">Connecting…</span>
          )}
        </div>
        <button className="reset-btn" onClick={reset} title="Start over">
          New chat
        </button>
      </div>

      <div className="messages">
        {messages.map((m, i) => (
          <Message
            key={i}
            message={m}
            onSuggestion={send}
            onPinModel={setModelNumber}
            pinnedModel={modelNumber}
          />
        ))}
        {showStarters && <SuggestedPrompts prompts={STARTER_PROMPTS} onPick={send} title="Try asking…" />}
        <div ref={scrollRef} />
      </div>

      <div className="composer">
        {modelNumber && <ModelPin model={modelNumber} onClear={() => setModelNumber(null)} />}
        <div className="composer-row">
          <textarea
            ref={taRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Ask about a part, model compatibility, installation, or a symptom…"
            rows="1"
            disabled={busy}
          />
          <button
            className="send-btn"
            onClick={() => send(input)}
            disabled={busy || !input.trim()}
            aria-label="Send"
          >
            {busy ? (
              <span className="spinner" />
            ) : (
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <path
                  d="M4 12 20 4l-4 16-4-6-8-2Z"
                  stroke="currentColor"
                  strokeWidth="1.9"
                  strokeLinejoin="round"
                  fill="currentColor"
                  fillOpacity="0.15"
                />
              </svg>
            )}
          </button>
        </div>
        <div className="composer-hint">
          Scoped to refrigerator &amp; dishwasher parts · press Enter to send
        </div>
      </div>
    </div>
  );
}

export default ChatWindow;
