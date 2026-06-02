"""Agent orchestrator.

Thin layer that the API calls. Responsibilities:
  - deterministic backstop for empty input
  - run the provider-agnostic tool loop
  - de-duplicate cards and cap follow-up suggestions
"""
from typing import List

from .llm import llm
from .prompts import EMPTY_INPUT_REPLY
from .tools import TOOL_SCHEMAS, execute_tool


def _dedupe_cards(cards: List[dict]) -> List[dict]:
    seen, out = set(), []
    for card in cards:
        # Identity by (type, ps_number/order_id) so the same product shown by two
        # tools in one turn isn't rendered twice.
        key = (
            card.get("type"),
            card.get("ps_number")
            or card.get("order_id")
            or (card.get("part") or {}).get("ps_number"),
            card.get("model_number"),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(card)
    return out


def run_agent(history: List[dict]) -> dict:
    """history: [{'role': 'user'|'assistant', 'content': str}], oldest first.
    Returns {'text', 'cards', 'suggestions', 'tools_used'}."""
    last_user = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
    if not last_user or not last_user.strip():
        return {"text": EMPTY_INPUT_REPLY, "cards": [], "suggestions": [], "tools_used": []}

    result = llm.converse(history, TOOL_SCHEMAS, execute_tool)
    result["cards"] = _dedupe_cards(result.get("cards", []))
    # Keep follow-up chips tidy: unique, max 3.
    seen, suggestions = set(), []
    for s in result.get("suggestions", []):
        if s not in seen:
            seen.add(s)
            suggestions.append(s)
    result["suggestions"] = suggestions[:3]
    return result
