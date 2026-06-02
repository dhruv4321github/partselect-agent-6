"""FastAPI entrypoint.

Endpoints:
  GET  /api/health         -> liveness + which provider/model is configured
  POST /api/chat           -> non-streaming JSON (simple, robust)
  POST /api/chat/stream     -> Server-Sent Events: token stream + cards + suggestions

The agent runs its tool loop fully before streaming. We then replay the final
answer token-by-token over SSE for a responsive typing effect, and emit a single
`meta` event carrying the structured cards/suggestions, then `done`. This keeps
streaming behaviour identical across LLM providers; swapping in native
provider token streaming is a localized change in llm.py.
"""
import asyncio
import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .agent import run_agent
from .config import settings
from . import live as live_module
from .schemas import ChatRequest, ChatResponse

app = FastAPI(title="PartSelect Assistant API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _history(req: ChatRequest):
    history = [{"role": m.role, "content": m.content} for m in req.messages]
    # If the user pinned a model number in the UI, attach it to their latest
    # message so the agent can resolve "my model" without re-asking.
    if req.model_number and history and history[-1]["role"] == "user":
        history[-1]["content"] += f"\n\n(My appliance model number is {req.model_number}.)"
    return history


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "provider": settings.provider,
        "model": settings.model,
        "api_key_configured": bool(settings.fallback_api_key()),
        "live": {
            "enabled": settings.live_fetch,
            "deps_available": live_module._DEPS,
            "resolve_via_sitemap": settings.live_resolve_via_sitemap,
        },
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    result = run_agent(_history(req))
    return ChatResponse(
        content=result["text"] or "Sorry, I couldn't generate a response. Please try rephrasing.",
        cards=result["cards"],
        suggestions=result["suggestions"],
        tools_used=result["tools_used"],
    )


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    history = _history(req)

    async def event_stream():
        # Run the (sync) agent loop off the event loop so we don't block.
        result = await asyncio.to_thread(run_agent, history)
        text = result["text"] or "Sorry, I couldn't generate a response. Please try rephrasing."

        # Stream the answer in word chunks for a typing effect.
        for chunk in _word_chunks(text):
            yield _sse("token", {"text": chunk})
            await asyncio.sleep(0.012)

        yield _sse("meta", {"cards": result["cards"],
                            "suggestions": result["suggestions"],
                            "tools_used": result["tools_used"]})
        yield _sse("done", {})

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _word_chunks(text: str):
    words = text.split(" ")
    for i, w in enumerate(words):
        yield (w if i == 0 else " " + w)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
