// ============================================================
//  API client for the PartSelect agent backend.
//
//  Primary path: POST /api/chat/stream (Server-Sent Events).
//    - `token` events stream the assistant text word-by-word
//    - one `meta` event carries structured cards + follow-up chips
//    - `done` closes the turn
//  Fallback path: POST /api/chat (single JSON response) if the
//  stream can't be opened, so the UI degrades gracefully.
//
//  The base URL is configurable; Next.js rewrites in next.config.mjs
//  proxy /api to localhost:8000 in dev.
// ============================================================

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "";

/**
 * Stream a chat turn.
 * @param {Array<{role,content}>} history  full conversation, oldest first
 * @param {string|null} modelNumber        optional pinned model ("your model")
 * @param {object} handlers                { onToken, onMeta, onDone, onError }
 */
export async function streamChat(history, modelNumber, handlers) {
  const { onToken, onMeta, onDone, onError } = handlers;
  try {
    const res = await fetch(`${API_BASE}/api/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: history, model_number: modelNumber || null }),
    });

    if (!res.ok || !res.body) throw new Error(`stream failed: ${res.status}`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE frames are separated by a blank line.
      const frames = buffer.split("\n\n");
      buffer = frames.pop() || "";

      for (const frame of frames) {
        const ev = parseSSE(frame);
        if (!ev) continue;
        if (ev.event === "token") onToken?.(extractToken(ev.data));
        else if (ev.event === "meta") onMeta?.(safeJSON(ev.data));
        else if (ev.event === "done") onDone?.();
      }
    }
    onDone?.();
  } catch (err) {
    // Fall back to the non-streaming endpoint so the user still gets a reply.
    try {
      await nonStreamingFallback(history, modelNumber, handlers);
    } catch (e) {
      onError?.(e);
    }
  }
}

async function nonStreamingFallback(history, modelNumber, { onToken, onMeta, onDone, onError }) {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages: history, model_number: modelNumber || null }),
  });
  if (!res.ok) {
    onError?.(new Error(`chat failed: ${res.status}`));
    return;
  }
  const data = await res.json();
  if (data.content) onToken?.(data.content); // deliver whole message at once
  onMeta?.({ cards: data.cards || [], suggestions: data.suggestions || [] });
  onDone?.();
}

// Parse one SSE frame into { event, data }.
function parseSSE(frame) {
  const lines = frame.split("\n");
  let event = "message";
  const dataLines = [];
  for (const line of lines) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).replace(/^ /, ""));
  }
  if (dataLines.length === 0) return null;
  return { event, data: dataLines.join("\n") };
}

function safeJSON(s) {
  try {
    return JSON.parse(s);
  } catch {
    return { cards: [], suggestions: [] };
  }
}

// Token events arrive as JSON: {"text": "the chunk"}. Unwrap to the bare string.
// Falls back to the raw data if it isn't JSON (e.g. the non-streaming path).
function extractToken(data) {
  try {
    const obj = JSON.parse(data);
    if (obj && typeof obj.text === "string") return obj.text;
  } catch {
    /* not JSON — treat as plain text */
  }
  return data;
}

/** Health probe used to show provider/model + whether a key is configured. */
export async function getHealth() {
  try {
    const res = await fetch(`${API_BASE}/api/health`);
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}
