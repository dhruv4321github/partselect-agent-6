# Loom walkthrough — talking points

A suggested structure for the video (~5–7 min). Demo first, then architecture — show
it working before explaining how. Times are rough.

---

## 0:00 — Framing (20s)

> "This is a chat agent for PartSelect, scoped to refrigerator and dishwasher parts.
> It answers product questions, checks compatibility, walks through installs,
> troubleshoots, and helps with cart and order tasks. I'll demo the three example
> queries, then walk through the architecture and how it scales."

Have the backend and frontend already running so you open straight to the chat.

---

## 0:20 — Demo the three brief queries (2.5 min)

Click the starter chips so it's fast. For each, point at the **card**, not just the text.

**1. Install** — *"How can I install part number PS11752778?"*
- Watch the text stream in, then the install card renders.
- Call out: numbered steps, difficulty + time badges, the part it resolved.
- Point: "The steps and difficulty come from the catalog tool — the model isn't
  making them up, it's narrating verified data."

**2. Compatibility** — *"Is part PS11752778 compatible with my WDT780SAEM1 model?"*
- This is the one to linger on. PS11752778 is a *fridge* door bin; WDT780SAEM1 is a
  *dishwasher*.
- Card shows a red ✕ "Not compatible" **and offers a part that does fit the model.**
- Point: "It didn't just say no — it reasoned across two catalog lookups and
  recovered with a useful alternative. That's the agentic loop, not a fixed flow."

**3. Repair** — *"The ice maker on my Whirlpool fridge is not working. How can I fix it?"*
- Repair card: ranked causes, each with a short explanation and **clickable part
  chips**, plus quick-checks.
- Click a part chip → it asks about that part → product card. Show the loop closing
  from symptom → cause → buyable part.

**Bonus (optional):** *"Where is my order PS-1042205?"* → order-status card with
tracking. And type an off-topic question ("what's a good microwave?") to show it
**declines and redirects** — proving scope enforcement.

---

## 2:50 — Architecture (2 min)

Pull up the README diagram or `tools.py`.

- **Agentic tool loop.** "The model is given 8 tools and decides which to call. The
  orchestrator runs them, feeds results back, and loops until it has an answer.
  Chaining like the compatibility-plus-alternative case falls out of this naturally —
  no hard-coded conversation flows."
- **"Model narrates, tools render."** "Every tool returns three things: a short text
  summary the model reads, structured cards that bypass the model and render as UI,
  and follow-up suggestions. That's the key UX decision — prose stays short, and
  prices/part numbers/steps stay exact because the model never rewrites them."
- **Grounding.** "The system prompt forbids inventing part numbers or compatibility.
  Everything comes from tool results, so it can't hallucinate a spec. I test that at
  the data layer with 14 unit tests that run without an API key."
- **Provider-agnostic.** "Thin LLM client — runs on Anthropic, OpenAI, Deepseek, or
  Groq by changing two env vars. Same tool loop, same cards."

---

## 4:50 — Extensibility & scale (1 min)

This is what they're evaluating for — say it explicitly.

- "The catalog sits behind two interfaces: `PartsRepository` and `SearchIndex`. Today
  that's a curated JSON catalog and keyword search."
- "For production you swap `SearchIndex` for a vector DB for semantic search, and back
  the repository with the real PartSelect catalog via scraper or internal API —
  **with zero changes to the tools, agent, or frontend.** That seam is the scalability
  story."
- "Adding scope — more appliance types — is a data and prompt change. Adding a
  capability is one new tool plus one card component. The architecture doesn't move."

---

## 5:50 — Close (20s)

> "So: an agent that's accurate because it's grounded in tools, a UX that's rich
> because tools render cards, and a structure that scales by swapping the data layer
> behind a stable interface. Scoped tightly to fridge and dishwasher today, but
> designed to widen cleanly."

---

### Reminders
- Start with the demo working on screen — don't open cold.
- Keep narrating *why*, not just *what* — the brief rewards design thinking.
- The compatibility-with-alternative moment and the "model narrates, tools render"
  point are the two things most worth landing.
