"""Provider-agnostic LLM client + agentic tool loop.

Supports two backends selected by LLM_PROVIDER:
  - "anthropic": uses the official `anthropic` SDK and Messages tool-use protocol.
  - "openai":    uses the `openai` SDK; with LLM_BASE_URL set this also covers
                 Deepseek, Groq, Together, or any OpenAI-compatible endpoint.

`converse()` runs the full tool loop server-side and returns the final text plus
the UI cards/suggestions collected from every tool result. Streaming to the
client is handled at the transport layer (see agent.py / main.py) so it stays
identical across providers.
"""
from typing import Callable, List

from .config import settings
from .prompts import SYSTEM_PROMPT


class LLMClient:
    def __init__(self):
        self.provider = settings.provider
        self.model = settings.model
        self.max_tokens = settings.max_tokens
        self.max_steps = settings.max_tool_steps
        self.api_key = settings.fallback_api_key()
        self.base_url = settings.base_url or None
        self._client = None  # lazy init so the app boots even without a key set

    # -- public API ------------------------------------------------------
    def converse(self, messages: List[dict], tools: List[dict], executor: Callable) -> dict:
        """messages: neutral [{'role': 'user'|'assistant', 'content': str}].
        executor(name, args) -> {'summary': str, 'cards': [...], 'suggestions': [...]}.
        Returns {'text', 'cards', 'suggestions', 'tools_used'}."""
        if self.provider == "anthropic":
            return self._converse_anthropic(messages, tools, executor)
        return self._converse_openai(messages, tools, executor)

    # -- Anthropic -------------------------------------------------------
    def _anthropic_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def _converse_anthropic(self, messages, tools, executor):
        client = self._anthropic_client()
        convo = [{"role": m["role"], "content": m["content"]} for m in messages]
        cards, suggestions, tools_used = [], [], []

        for _ in range(self.max_steps):
            resp = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM_PROMPT,
                tools=tools,
                messages=convo,
            )
            if resp.stop_reason != "tool_use":
                text = "".join(b.text for b in resp.content if b.type == "text")
                return {"text": text.strip(), "cards": cards,
                        "suggestions": suggestions, "tools_used": tools_used}

            # Record the assistant's tool-use turn verbatim.
            convo.append({"role": "assistant", "content": resp.content})
            tool_results = []
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                tools_used.append(block.name)
                result = executor(block.name, dict(block.input or {}))
                cards.extend(result.get("cards", []))
                suggestions.extend(result.get("suggestions", []))
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result.get("summary", ""),
                })
            convo.append({"role": "user", "content": tool_results})

        # Hit the step cap -> ask the model for a final answer with no tools.
        resp = client.messages.create(
            model=self.model, max_tokens=self.max_tokens,
            system=SYSTEM_PROMPT, messages=convo,
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        return {"text": text.strip(), "cards": cards,
                "suggestions": suggestions, "tools_used": tools_used}

    # -- OpenAI-compatible (OpenAI / Deepseek / Groq / ...) --------------
    def _openai_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._client

    def _converse_openai(self, messages, tools, executor):
        client = self._openai_client()
        oa_tools = [{"type": "function", "function": {
            "name": t["name"], "description": t["description"],
            "parameters": t["input_schema"]}} for t in tools]
        convo = [{"role": "system", "content": SYSTEM_PROMPT}]
        convo += [{"role": m["role"], "content": m["content"]} for m in messages]
        cards, suggestions, tools_used = [], [], []

        import json
        for _ in range(self.max_steps):
            resp = client.chat.completions.create(
                model=self.model, max_tokens=self.max_tokens,
                messages=convo, tools=oa_tools, tool_choice="auto",
            )
            msg = resp.choices[0].message
            if not msg.tool_calls:
                return {"text": (msg.content or "").strip(), "cards": cards,
                        "suggestions": suggestions, "tools_used": tools_used}

            convo.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [{
                    "id": tc.id, "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                } for tc in msg.tool_calls],
            })
            for tc in msg.tool_calls:
                tools_used.append(tc.function.name)
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = executor(tc.function.name, args)
                cards.extend(result.get("cards", []))
                suggestions.extend(result.get("suggestions", []))
                convo.append({"role": "tool", "tool_call_id": tc.id,
                              "content": result.get("summary", "")})

        resp = client.chat.completions.create(
            model=self.model, max_tokens=self.max_tokens, messages=convo)
        return {"text": (resp.choices[0].message.content or "").strip(),
                "cards": cards, "suggestions": suggestions, "tools_used": tools_used}


llm = LLMClient()
