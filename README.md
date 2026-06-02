# PartSelect Parts Assistant

A chat agent for **PartSelect.com**, scoped to **Refrigerator** and **Dishwasher**
parts. It answers product questions, checks model compatibility, walks through
installations, troubleshoots symptoms, and assists with cart/order tasks — and
it politely declines anything outside that scope.

It is built around a real **agentic tool-calling loop**: the model decides which
catalog tools to call, the orchestrator runs them and feeds results back, and the
final answer is grounded in returned data rather than the model's memory.

```
┌──────────────────────────────────────────────────────────────────────┐
│  React frontend (CRA)                                                  │
│  ChatWindow ── streams tokens ──► rich cards (product / compatibility  │
│       │                            / install / repair / order / cart)  │
└───────┼────────────────────────────────────────────────────────────────┘
        │  POST /api/chat/stream  (Server-Sent Events)
        ▼
┌──────────────────────────────────────────────────────────────────────┐
│  FastAPI backend                                                        │
│                                                                         │
│   agent.run_agent()                                                     │
│        │   empty-input backstop · card de-dupe · suggestion cap         │
│        ▼                                                                │
│   LLMClient.converse()   ◄──── provider-agnostic (Anthropic | OpenAI-   │
│        │   tool loop                compatible: OpenAI / Deepseek / Groq)│
│        ▼                                                                │
│   execute_tool(name,args)  ──►  8 tools                                 │
│        │                         search · details · compatibility ·     │
│        ▼                         install · repair · model · order · cart│
│   PartsRepository  ◄── SearchIndex (the swap-for-vector-DB seam)        │
│        │                                                                │
│        ▼                                                                │
│   curated JSON catalog  (parts · models · repair guides · orders)       │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Quick start

You need **Python 3.10+**, **Node 18+**, and one LLM API key.

### 1. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # then paste your key into .env
uvicorn app.main:app --reload --port 8000
```

Sanity check: `curl localhost:8000/api/health` should report your provider,
model, and `"api_key_configured": true`.

### 2. Frontend

```bash
cd frontend
npm install
npm start                      # opens http://localhost:3000
```

The dev server proxies `/api` to `localhost:8000`, so no extra config is needed.

### 3. Try it

The three brief prompts are wired as starter chips:
- *How can I install part number PS11752778?*
- *Is part PS11752778 compatible with my WDT780SAEM1 model?*
- *The ice maker on my Whirlpool fridge is not working. How can I fix it?*

Plus transaction/model examples like *"What parts fit my WDT780SAEM1 dishwasher?"*
and *"Where is my order PS-1042205?"*

---

## Choosing an LLM provider

The agent is **provider-agnostic** — it runs with whatever key you have. Set these
in `backend/.env` (see `.env.example` for ready-made blocks):

| Provider  | `LLM_PROVIDER` | `LLM_MODEL` (example)        | Extra                                  |
|-----------|----------------|------------------------------|----------------------------------------|
| Anthropic | `anthropic`    | `claude-sonnet-4-6`          | `ANTHROPIC_API_KEY`                    |
| OpenAI    | `openai`       | `gpt-4o-mini`                | `OPENAI_API_KEY`                       |
| Deepseek  | `openai`       | `deepseek-chat`              | `OPENAI_API_KEY` + `LLM_BASE_URL`      |
| Groq      | `openai`       | `llama-3.3-70b-versatile`    | `OPENAI_API_KEY` + `LLM_BASE_URL`      |

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
   prose short while the data stays exact (prices, part numbers, steps are never
   paraphrased by the model).
5. The backend replays the final text over SSE word-by-word, then sends one `meta`
   event with the cards/suggestions, then `done`.

---

## Key design decisions

**Agentic tool loop, not retrieval-then-answer.** The model picks tools in sequence,
so it can chain (e.g. look up a part, then check it against a model, then suggest an
alternative) without hard-coded flows. New capabilities = new tools.

**Grounding over recall.** The system prompt forbids inventing part numbers, prices,
or compatibility. Facts come only from tool results, so the agent can't hallucinate a
spec. Tests assert this at the data layer independently of the model.

**Structured cards separate from prose.** Returning data as cards (not as text the
model rewrites) is what keeps the UX rich *and* accurate, and it's the main
extensibility seam on the frontend — a new card type is one component + one `case`.

**Scope enforcement, two layers.** A strict system prompt declines and redirects
off-topic / non-fridge-dishwasher requests, backed by a deterministic empty-input
guard. Refrigerator + dishwasher today; widening scope is a data + prompt change, not
an architecture change.

**Provider-agnostic by default.** A thin `LLMClient` abstracts Anthropic vs
OpenAI-compatible APIs so the project runs on whatever key a reviewer has.

---

## Extensibility & scalability

The catalog sits behind two interfaces, `PartsRepository` and `SearchIndex`, which is
where this scales from a demo to production:

- **Today:** a curated JSON catalog and a dependency-free hybrid keyword search
  (field-weighted token overlap). Zero infra, instant to run.
- **Production swap:** replace `SearchIndex` with a vector DB (pgvector / Pinecone /
  Weaviate) for semantic part search, and back `PartsRepository` with the real
  PartSelect catalog via a scraper or internal API. **No tool, agent, or frontend code
  changes** — the tools call the same repository methods. A working implementation of
  the ingestion half ships in `backend/scripts/` (`scrape_partselect.py`): a
  robots-compliant, sitemap-driven crawler that emits the exact `parts.json` shape the
  repository already reads. See `backend/scripts/README.md` for the robots.txt /
  sitemap findings behind it.

Other natural extensions: more appliance categories (add data + widen the scope
prompt), real cart/checkout and order APIs (the cart/order tools are mock
implementations with production-shaped payloads), per-user model memory (the "pin your
model" mechanism already threads a model number through every request), and native
token streaming (currently the loop runs server-side then replays; switching to true
token streaming is localized to `LLMClient`).

### Hybrid live mode & PartSelect's bot protection

The repository has a live fallback (`backend/app/live.py`): for any part/model not
in the local catalog it fetches the page from partselect.com, parses it into the same
dict shapes, caches it, persists it to `data/*.json`, and serves it through the same
tools and cards. The high-value path is the model page (`…/Models/{MODEL}/`) — a
deterministic URL returning the model plus its parts in one request.

**The catch, found by testing:** PartSelect sits behind Akamai bot protection that
returns **HTTP 403** to server-side `requests` on the first request, regardless of
User-Agent or headers — it fingerprints the TLS/HTTP handshake, which a real browser
satisfies and `requests` does not. So **live fetch is off by default.** To turn it on:

```bash
pip install curl_cffi      # impersonates a real browser's TLS fingerprint
# set LIVE_FETCH=true in .env, then restart
```

With `curl_cffi` present, the client routes all requests through it (`impersonate=
"chrome"`), which gets past the 403 in most cases. The code degrades gracefully: no
`curl_cffi` or a hard block → it logs the reason (`[live] HTTP 403 …`) and the app
keeps serving the curated catalog. The honest production answer isn't "scrape harder"
— it's a **licensed data feed or catalog partnership** behind the same
`PartsRepository` interface; the live code demonstrates the ingestion/parsing approach.
Compatibility is reported conservatively either way: a part absent from a model's
(partial) live list is *unconfirmed*, never a false "no."

---

## Project layout

```
partselect-agent/
├── backend/
│   ├── app/
│   │   ├── main.py          FastAPI app: /api/health, /api/chat, /api/chat/stream
│   │   ├── agent.py         orchestrator: backstop, card de-dupe, suggestion cap
│   │   ├── llm.py           provider-agnostic client + tool loop (Anthropic/OpenAI)
│   │   ├── tools.py         8 tool schemas + implementations → {summary,cards,suggestions}
│   │   ├── catalog.py       PartsRepository (lookup, compatibility, repair, orders)
│   │   ├── live.py          PartSelectClient: optional live fetch + parse + cache
│   │   ├── search.py        SearchIndex (the vector-DB seam)
│   │   ├── prompts.py       system prompt: persona, strict scope, grounding rules
│   │   ├── schemas.py       Pydantic request/response models
│   │   └── config.py        env-driven settings
│   ├── data/                parts · models · repair_help · orders  (JSON)
│   ├── tests/test_agent.py  14 unit tests (run without an API key)
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    └── src/
        ├── ChatWindow.js    streaming chat, starter chips, model pin, health
        ├── Message.js       markdown bubble + card dispatch + follow-up chips
        ├── api/api.js       SSE client with non-streaming fallback
        └── components/cards/  Product · Compatibility · Install · Repair · Order · Cart
```

---

## A note on the data

The app ships with a **curated, hand-verified catalog** (`data/parts.json`,
`data/models.json` — 17 parts, 6 models) so the demo works fully offline and
deterministically. The featured items are real PartSelect data: PS11752778 (the
Whirlpool door bin), the WDT780SAEM1 dishwasher, and their manufacturer numbers,
prices, symptoms, and compatibility come from the live listings. (`parts.sample.json` /
`models.sample.json` are identical backups, used by the tests.)

When **live mode is enabled** (see above — requires `curl_cffi`), anything not already
in the catalog is fetched on demand and **persisted back into `data/*.json`**, so the
local catalog grows over time and repeat queries are served from disk. Fetched HTML is
also cached under `data/.live_cache/`. For a blank-slate, live-first setup you can empty
`parts.json`/`models.json` to `[]`.

`repair_help.json` and `orders.json` are mock/demo data (no 1:1 live source). In
production the whole catalog layer is replaced by a data feed behind the same
`PartsRepository` interface.

---

## Tests

```bash
cd backend && python -m pytest tests/ -v
```

The suite runs without an API key — it exercises the catalog and tool logic the agent
grounds its answers in, so the data is verified independently of the model.

---

## Notes

- The frontend is the provided Create React App starter, upgraded in place. It drops
  into Next.js with minimal changes (components are framework-agnostic; the SSE client
  in `api/api.js` is plain `fetch`).
- `LLM_MAX_TOKENS`, `AGENT_MAX_TOOL_STEPS`, and `CORS_ORIGINS` are tunable via env.
