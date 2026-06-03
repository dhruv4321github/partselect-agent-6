# PartSelect Parts Assistant

A conversational agent for **PartSelect.com**, scoped to **Refrigerator** and
**Dishwasher** parts. It answers product questions, checks model compatibility,
walks through installations, troubleshoots symptoms with model-specific
diagnosis, and manages a shopping cart — and it politely declines anything
outside that scope.

It is built around an **agentic tool-calling loop**: the model decides which
tools to call, the orchestrator runs them and feeds results back, and the final
answer is grounded in returned data rather than the model's memory.

```
┌──────────────────────────────────────────────────────────────────────┐
│  Next.js frontend (App Router)                                       │
│  ChatWindow ── streams tokens ──► rich cards (product /              │
│       │                           compatibility / cart)              │
└───────┼──────────────────────────────────────────────────────────────┘
        │  POST /api/chat/stream  (Server-Sent Events)
        ▼
┌──────────────────────────────────────────────────────────────────────┐
│  FastAPI backend                                                     │
│                                                                      │
│   agent.run_agent()                                                  │
│        │   empty-input backstop · card de-dupe · suggestion cap      │
│        ▼                                                             │
│   LLMClient.converse()   ◄── provider-agnostic (Anthropic | OpenAI   │
│        │   tool loop                 -compatible: OpenAI / etc.)     │
│        ▼                                                             │
│   execute_tool(name,args)  ──►  10 tools                             │
│        │                         search · details · compatibility ·  │
│        │                         install · repair · symptom guide ·  │
│        │                         model parts · model diagnosis ·     │
│        ▼                         cart (add/view/remove)              │
│   PartsRepository  ◄── SearchIndex + PartSelectClient (live)         │
│        │                                                             │
│        ▼                                                             │
│   on-demand live scraping ── cached to disk ── persisted to JSON     │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Quick start

You need **Python 3.10+**, **Node 18+**, and one LLM API key.

### 1. Backend

```bash
cd backend
pip install -r requirements.txt
pip install curl_cffi                                 # required for live fetch
cp .env.example .env                                 # then paste your key into .env
uvicorn app.main:app --reload --port 8000
```

Sanity check: `curl localhost:8000/api/health` should report your provider,
model, and `"api_key_configured": true`.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev                    # opens http://localhost:3000
```

Next.js rewrites `/api` requests to `localhost:8000` (configured in
`next.config.mjs`), so no extra config is needed.

### 3. Try it

Starter chips on the welcome screen:
- *How can I install part number PS11752778?*
- *Is part PS11752778 compatible with my WDT780SAEM1 model?*
- *The ice maker on my Whirlpool fridge is not working. How can I fix it?*

Plus model-specific queries like *"What parts fit my WDT780SAEM1 dishwasher?"*

---

## Choosing an LLM provider

The agent is **provider-agnostic** — it runs with whatever key you have. Set these
in `backend/.env` (see `.env.example` for ready-made blocks):

| Provider  | `LLM_PROVIDER` | `LLM_MODEL` (example)        | Extra                                  |
|-----------|----------------|------------------------------|----------------------------------------|
| OpenAI    | `openai`       | `gpt-4o-mini` (recommended)  | `OPENAI_API_KEY`                       |
| Anthropic | `anthropic`    | `claude-sonnet-4-6`          | `ANTHROPIC_API_KEY`                    |
| Deepseek  | `openai`       | `deepseek-chat`              | `OPENAI_API_KEY` + `LLM_BASE_URL`      |
| Groq      | `openai`       | `llama-3.3-70b-versatile`    | `OPENAI_API_KEY` + `LLM_BASE_URL`      |

**Why `gpt-4o-mini`?** We tested with OpenAI's `gpt-4.1-mini` and found no
meaningful improvement in tool-calling accuracy or response quality for this
task, and latency was comparable. `gpt-4o-mini` is the better value for a
multi-turn, tool-heavy agent like this.

Anthropic uses the native Messages tool-use protocol; everything OpenAI-compatible
goes through the OpenAI tool-calling path. Both run the same tool loop and produce
the same cards.

---

## How a turn works

1. The frontend POSTs the conversation (plus any pinned model number) to
   `/api/chat/stream`.
2. `run_agent` runs an empty-input backstop, then calls the LLM.
3. The model may emit tool calls. The orchestrator executes each tool, appends the
   result, and loops — up to `AGENT_MAX_TOOL_STEPS` (default 6) — until the model
   produces a final answer.
4. **"Model narrates, tools render."** Each tool returns three things: a short text
   `summary` the model reads to write its reply, structured `cards` that bypass the
   model and render as rich UI, and optional follow-up `suggestions`. This keeps the
   prose short while the data stays exact (prices, part numbers, fix percentages are
   never paraphrased by the model).
5. The backend replays the final text over SSE word-by-word, then sends one `meta`
   event with the cards/suggestions, then `done`.

---

## Key design decisions

### Live-first, on-demand scraping

Instead of pre-scraping the entire PartSelect catalog upfront (millions of pages),
the agent fetches data **on demand** — only when a customer asks about a specific
part or model. This has significant advantages:

- **Always up-to-date.** Prices, stock status, and compatibility come from the
  live site at query time, not from a stale snapshot.
- **Zero ingestion pipeline.** No cron jobs, no ETL, no batch scraping
  infrastructure. The catalog bootstraps itself from an empty `[]`.
- **Grows organically.** Every query enriches the local cache. Popular
  parts/models are served from disk on repeat queries; long-tail items are
  fetched on first request and cached for next time.
- **Polite and targeted.** Instead of hammering the site with a full crawl, we
  make a handful of focused requests per conversation turn.

The tradeoff is **first-query latency**: a part/model not yet in the cache
requires live HTTP requests. Model pages are fast (one deterministic URL), but
part lookups need URL resolution since PartSelect's canonical part URLs contain
a slug that isn't derivable from the PS number alone. Resolution works via a
**sitemap index** -- a one-time download of PartSelect's sitemap XML files that
maps all ~100K PS numbers to their full URLs, cached locally as
`ps_url_index.json`. After the first build, lookups are instant dictionary reads.
Repeat queries for any entity are served from disk. In production, this
cold-start cost could be mitigated with a warm-up script that pre-fetches
high-traffic models, or by replacing the scraper with a licensed data feed
behind the same `PartsRepository` interface.

### Agentic tool loop, not retrieval-then-answer

The model picks tools in sequence, so it can chain operations (e.g. look up a
part, then check it against a model, then suggest an alternative) without
hard-coded flows. New capabilities = new tools.

### Grounding over recall

The system prompt forbids inventing part numbers, prices, or compatibility. Facts
come only from tool results, so the agent can't hallucinate a spec. Anti-hallucination
instructions are embedded at multiple levels: the system prompt, individual tool
summaries, and explicit "do NOT guess" directives when the data is ambiguous. Tests
assert this at the data layer independently of the model.

### Structured cards separate from prose

Returning data as cards (not as text the model rewrites) keeps the UX rich *and*
accurate, and it's the main extensibility seam on the frontend -- a new card type
is one component + one `case` in `Message.js`. Every tool that surfaces a part
(install guide, compatibility check, search, model diagnosis) returns a product
card alongside the text summary, so the user always has the image, price, and
direct link to PartSelect without relying on the LLM to include them.

### Scope enforcement, two layers

A strict system prompt declines and redirects off-topic / non-fridge-dishwasher
requests, backed by a deterministic empty-input guard. Refrigerator + dishwasher
today; widening scope is a data + prompt change, not an architecture change.

### Multi-step repair flow

Troubleshooting follows a deliberate escalation path:
1. **Generic diagnosis** — `get_repair_help` searches PartSelect's repair index
   for the appliance type + symptom, returning common causes and fixes.
2. **Symptom detail** — `get_symptom_repair_guide` fetches the full repair page
   for a specific symptom with detailed causes and part categories.
3. **Model-specific diagnosis** — `diagnose_model_symptom` fetches the symptom
   page for a specific model number, returning exact parts ranked by fix
   percentage (e.g. "76% of the time this is fixed by replacing the ice maker
   kit"). This is the highest-value step: it gives the customer a concrete,
   data-backed answer.

The LLM orchestrates these steps naturally through the tool loop, asking the
customer for their model number after the generic diagnosis, then automatically
calling the model-specific tool.

---

## Extensibility & scalability

The catalog sits behind two interfaces, `PartsRepository` and `SearchIndex`, which
is where this scales from a demo to production:

- **Today:** on-demand live scraping with local JSON caching and a dependency-free
  hybrid keyword search (field-weighted token overlap). Zero infra, instant to run.
- **Production swap:** replace `SearchIndex` with a vector DB (pgvector / Pinecone /
  Weaviate) for semantic part search, and back `PartsRepository` with a licensed
  catalog feed. **No tool, agent, or frontend code changes** — the tools call the
  same repository methods.

### Scaling the live approach

The on-demand architecture naturally supports several scaling strategies:

- **Cache warming.** Pre-fetch the top N most-searched models during off-peak hours
  so most customer queries hit the local cache.
- **TTL-based refresh.** Add expiration timestamps to cached entries and re-fetch
  stale data in the background, keeping prices and stock accurate without full
  re-scrapes.
- **Read replicas.** The JSON files can be replaced with a database (Postgres,
  Redis) for concurrent access across multiple backend instances.
- **Data feed migration.** The `PartsRepository` interface is the seam: swap the
  live scraper for a licensed PartSelect data feed or internal API, and the rest
  of the stack — tools, agent, frontend — stays identical.

### Adding capabilities

- **More appliance types** — add data + widen the scope prompt. The architecture
  doesn't change.
- **New tool** — define a schema in `tools.py`, implement the function, register
  it. The LLM discovers it automatically.
- **New card type** — one React component + one `case` in `Message.js`.
- **Real checkout** — the cart tools already produce production-shaped payloads.
  Wire them to a real checkout API behind the same interface.
- **Per-user model memory** — the "pin your model" mechanism already threads a
  model number through every request; persisting it per session/user is a small
  extension.

---

## PartSelect's bot protection

PartSelect sits behind Akamai bot protection that returns **HTTP 403** to
plain `requests` and **HTTP 500** for short-form part URLs -- it fingerprints
the TLS/HTTP handshake, which a real browser satisfies and server-side HTTP
clients do not. To work around this:

```bash
pip install curl_cffi      # impersonates a real browser's TLS fingerprint
# set LIVE_FETCH=true in .env, then restart
```

With `curl_cffi`, the client impersonates Chrome's TLS fingerprint
(`impersonate="chrome"`), which gets past the 403 for page fetches (model
pages, part pages, symptom pages, sitemaps). Part URL resolution uses the
**sitemap index** rather than short-URL redirects, since PartSelect returns 500
for `/PSxxxxx.htm` even with browser impersonation. The code degrades
gracefully: no `curl_cffi` or a hard block -> it logs the reason and the app
keeps serving whatever is already cached. The honest production answer isn't
"scrape harder" -- it's a **licensed data feed** behind the same
`PartsRepository` interface; the live scraper demonstrates the
ingestion/parsing approach and keeps the demo fully functional.

Compatibility is reported conservatively: a part absent from a model's (partial)
live list is *unconfirmed*, never a false "no."

---

## Project layout

```
partselect-agent/
├── backend/
│   ├── app/
│   │   ├── main.py          FastAPI app: /api/health, /api/chat, /api/chat/stream
│   │   ├── agent.py         orchestrator: backstop, card de-dupe, suggestion cap
│   │   ├── llm.py           provider-agnostic client + tool loop (Anthropic/OpenAI)
│   │   ├── tools.py         10 tool schemas + implementations → {summary,cards,suggestions}
│   │   ├── catalog.py       PartsRepository (lookup, compatibility, search, repair)
│   │   ├── live.py          PartSelectClient: on-demand live fetch + parse + cache
│   │   ├── search.py        SearchIndex (the vector-DB seam)
│   │   ├── prompts.py       system prompt: persona, strict scope, grounding rules
│   │   ├── schemas.py       Pydantic request/response models
│   │   └── config.py        env-driven settings
│   ├── data/                parts.json · models.json (auto-populated by live fetch)
│   ├── tests/               16 unit tests (run without an API key)
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── app/
    │   ├── layout.js        root layout: meta, fonts, header shell
    │   └── page.js          "use client" entry → ChatWindow
    ├── next.config.mjs      API rewrite: /api → localhost:8000
    └── src/
        ├── ChatWindow.js    streaming chat, starter chips, model pin, health
        ├── Message.js       markdown bubble + card dispatch + follow-up chips
        ├── api/api.js       SSE client with non-streaming fallback
        └── components/cards/  ProductCard · CompatibilityCard · CartCard
```

---

## Data model

The app ships with **empty JSON files** (`data/parts.json`, `data/models.json`)
and populates them on demand via live scraping. There is no pre-seeded catalog —
every part and model in the system was fetched from PartSelect.com at query time
and cached locally.

When live mode is enabled (`LIVE_FETCH=true`), any part or model not in the local
cache is fetched, parsed into the standard dict shapes, and **persisted back into
`data/*.json`** so repeat queries are served from disk. Fetched HTML is also cached
under `.live_cache/`.

For a clean slate, reset both files to `[]` and restart the server.

---

## Tradeoffs & limitations

| Decision | Upside | Downside |
|----------|--------|----------|
| On-demand scraping vs. full crawl | Always fresh, zero ingestion infra, polite to the host | First-query latency (~2-5s per uncached entity) |
| JSON file storage vs. database | Zero-dependency, easy to inspect/reset | No concurrent writes, doesn't scale past a single instance |
| `gpt-4o-mini` vs. larger models | Fast, cheap, good enough for tool-calling | Occasionally needs explicit anti-hallucination instructions |
| Keyword search vs. vector/semantic | No embedding model dependency, instant | Misses synonyms and fuzzy matches |
| Scraper parsing HTML selectors | Works with the current PartSelect markup | Fragile to site redesigns (degrades gracefully, never crashes) |
| Appliance scope (fridge + dishwasher) | Tight, testable, demonstrable | Would need prompt + data changes to widen |

---

## Tests

```bash
cd backend && python -m pytest tests/ -v
```

The suite runs without an API key — it exercises the catalog, tool logic, and
live parsing that the agent grounds its answers in, so the data layer is verified
independently of the model.

---

## Notes

- The frontend uses Next.js (App Router) with all components as client-side React.
- `LLM_MAX_TOKENS`, `AGENT_MAX_TOOL_STEPS`, and `CORS_ORIGINS` are tunable via env.
- The install "steps" shown in product cards are real customer repair stories
  scraped from PartSelect's product pages (the `.repair-story` section), not
  LLM-generated content.
- Parts can be looked up by PartSelect number (PS...), manufacturer number, or
  older cross-reference numbers (e.g. AP6019471 resolves to PS11752778). Cross-
  reference lookup works from the local cache; PartSelect does not expose a URL
  for these numbers, so they require the canonical part to be cached first.
