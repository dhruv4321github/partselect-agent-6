"""
Unit tests for the PartSelect agent's deterministic layers (catalog, tools,
scope backstop). These run WITHOUT an LLM API key — they exercise the tool
implementations and repository logic the model depends on, so the data the
agent grounds its answers in is verified independently of the model.

Run:  cd backend && python -m pytest tests/ -v
"""
from app.tools import execute_tool, repo
from app.agent import run_agent


# ── Catalog / repository ──────────────────────────────────────────────

def test_lookup_by_ps_number():
    part = repo.get_part("PS11752778")
    assert part is not None
    assert part["mfr_number"] == "WPW10321304"
    assert part["appliance_type"] == "Refrigerator"


def test_lookup_by_mfr_number():
    part = repo.get_part("WPW10321304")
    assert part is not None
    assert part["ps_number"] == "PS11752778"


def test_unknown_part_returns_none():
    assert repo.get_part("PS00000000") is None


# ── Compatibility (example query #2) ──────────────────────────────────

def test_part_compatible_with_correct_model():
    r = execute_tool("check_compatibility",
                     {"part_number": "PS11752778", "model_number": "WRS325SDHZ08"})
    assert r["cards"][0]["compatible"] is True


def test_compatibility_unknown_model_is_honest():
    """An unrecognized model must not be guessed as a confident yes."""
    r = execute_tool("check_compatibility",
                     {"part_number": "PS11752778", "model_number": "ZZZ999"})
    card = r["cards"][0]
    assert card["compatible"] is not True


# ── Installation (example query #1) ───────────────────────────────────

def test_installation_guide_has_summary():
    r = execute_tool("get_installation_guide", {"part_number": "PS11752778"})
    assert "Installation info" in r["summary"]
    assert "PS11752778" in r["summary"]


# ── Search ────────────────────────────────────────────────────────────

def test_search_returns_only_products():
    r = execute_tool("search_parts", {"query": "door shelf", "appliance_type": "Refrigerator"})
    assert r["cards"]
    assert all(c["type"] == "product" for c in r["cards"])


# ── Cart ──────────────────────────────────────────────────────────────

def test_add_to_cart_computes_line_total():
    from app.tools import cart as _cart
    _cart.clear()
    r = execute_tool("add_to_cart", {"part_number": "PS11752778", "quantity": 2})
    card = next(c for c in r["cards"] if c["type"] == "cart")
    assert card["item_count"] >= 2
    assert card["total"] > 0
    item = card["items"][0]
    assert item["quantity"] == 2
    assert round(item["line_total"], 2) == round(item["price"] * 2, 2)
    _cart.clear()


# ── Tool error handling ───────────────────────────────────────────────

def test_execute_unknown_tool_is_guarded():
    r = execute_tool("does_not_exist", {})
    assert "summary" in r


# ── Scope backstop (deterministic, no model needed) ───────────────────

def test_empty_input_backstop():
    out = run_agent([{"role": "user", "content": "   "}])
    assert out["text"]
    assert out["cards"] == []
