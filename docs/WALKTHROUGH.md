# Loom walkthrough — talking points

A suggested structure for the video (~5–7 min). Demo first, then architecture — show
it working before explaining how. Times are rough.

---

## 0:00 — Framing (20s)

> "This is a chat agent for PartSelect, scoped to refrigerator and dishwasher parts.
> It finds parts, checks compatibility, diagnoses symptoms with model-specific fix
> data, and manages a shopping cart. Everything is live — there's no pre-scraped
> database. I'll demo it, then walk through the architecture."

Have the backend and frontend already running so you open straight to the chat.

---

## 0:20 — Demo (3.5 min)

Click the starter chips where available so it's fast. For each, point at the
**card**, not just the text.

**1. Install** — *"How can I install part number PS11752778?"*
- Text streams in with numbered steps, difficulty ("Really Easy"), time estimate
  ("Less than 15 minutes"), and tools needed ("None").
- A video guide link and a "View on PartSelect" link appear.
- Point: "These install steps are real customer repair stories scraped from the
  PartSelect product page — not LLM-generated. The agent fetched this live."

**2. Compatibility check** — *"Is PS11752778 compatible with my model?"*
- The agent asks for the model number (it doesn't know it yet).
- Give it: *"The model number is 10640262010."*
- Compatibility card shows a green checkmark: "confirmed compatible with model
  10640262010."
- Point: "It chained two tool calls — part lookup, then compatibility check
  against the model. That's the agentic loop, not a fixed flow."

**3. Troubleshooting flow** — *"The ice maker in my refrigerator is not working. How do I fix it?"*
- The agent first calls `get_repair_help` and returns generic causes: water fill
  tubes, water inlet valve, ice & water filter, ice maker assembly. It links to
  the full guide.
- Then it asks: *"Please provide your model number."*
- Give it: *"The model number of the refrigerator is 10640262010."*
- Now it calls `diagnose_model_symptom` and returns **model-specific parts ranked
  by fix percentage**:
  - Ice Maker Kit-PKG Assembly (PS17629131) — $146.56, **76% fix likelihood**
  - Refrigerator Crisper Drawer with Humidity Control (PS11739119) — $88.88, **17%**
  - Adhesive Cement (PS11742366) — **7%**, out of stock
- Product cards render with images, prices, "Add to cart" and "View on PartSelect"
  buttons.
- Point: "This is the most valuable step — model-specific parts with exact fix
  percentages, all from PartSelect's live data. The model never invents these
  numbers."

**4. Model parts lookup** — *"What parts are compatible with my dishwasher with model number WDT780SAEM1?"*
- 12 product cards render: Lower Dishrack Wheel, Upper Rack Adjuster Kit,
  Drain Pump, Door Seal, etc. — each with price, stock status, and description.
- Point: "One tool call fetched the model page, parsed all 12 parts, and
  persisted them to the local cache. Next time someone asks about this model,
  it's instant."

**5. Cart** — *"Add PS3406971 to my cart"*
- Cart card shows: 1 × Lower Dishrack Wheel, $33.69 total.
- Point: "The cart is session-based and produces production-shaped payloads —
  wiring it to a real checkout API is a backend change, not an architecture one."

**6. Scope enforcement** — Type an off-topic question ("what's a good microwave?")
- It **declines and redirects** to fridge/dishwasher parts.

---

## 3:50 — Architecture (2 min)

Pull up the README diagram or `tools.py`.

- **Agentic tool loop.** "The model is given 10 tools and decides which to call.
  The orchestrator runs them, feeds results back, and loops until it has an answer.
  Chaining like the compatibility case — where it asked for my model, then checked
  it — falls out of this naturally. No hard-coded conversation flows."
- **"Model narrates, tools render."** "Every tool returns three things: a short text
  summary the model reads, structured cards that bypass the model and render as UI,
  and follow-up suggestions. Prose stays short, and prices/part numbers/fix
  percentages stay exact because the model never rewrites them."
- **Live-first data.** "There's no pre-built database. The app starts with empty
  JSON files. When a customer asks about a part or model, the backend fetches the
  page from PartSelect, parses it, caches it, and persists it. Every piece of data
  in the system was fetched on demand and is always up to date."
- **Grounding.** "The system prompt forbids inventing part numbers or compatibility.
  Anti-hallucination rules are layered: system prompt, tool-level instructions, and
  explicit 'do NOT guess' directives. 16 unit tests verify this at the data layer
  without an API key."
- **Provider-agnostic.** "Thin LLM client — runs on OpenAI, Anthropic, or any
  OpenAI-compatible API by changing two env vars. We use gpt-4o-mini — tested
  against gpt-4.1-mini and found no meaningful improvement for this task, with
  comparable latency."

---

## 5:50 — Extensibility & scale (1 min)

This is what they're evaluating for — say it explicitly.

- "The catalog sits behind `PartsRepository` and `SearchIndex`. Today that's
  on-demand live scraping with JSON caching and keyword search."
- "For production you swap `SearchIndex` for a vector DB for semantic search, and
  back the repository with a licensed data feed or internal API — **with zero
  changes to the tools, agent, or frontend.** That seam is the scalability story."
- "The live approach scales naturally: cache warming for popular models, TTL-based
  refresh for price accuracy, and the JSON files can be swapped for a proper
  database for concurrent access."
- "Adding scope — more appliance types — is a data and prompt change. Adding a
  capability is one new tool plus one card component. The architecture doesn't move."

---

## 6:50 — Close (20s)

> "So: an agent that's accurate because it's grounded in live tool results, a UX
> that's rich because tools render cards, a data layer that's always fresh because
> it scrapes on demand, and a structure that scales by swapping the data layer
> behind a stable interface. Scoped tightly to fridge and dishwasher today, but
> designed to widen cleanly."

---

### Reminders
- Start with the demo working on screen — don't open cold.
- Clear `data/parts.json` and `data/models.json` to `[]` before recording if you
  want to show the "starts empty, grows on demand" story.
- Keep narrating *why*, not just *what* — the brief rewards design thinking.
- The live-fetched fix percentages and the "model narrates, tools render" point
  are the two things most worth landing.
