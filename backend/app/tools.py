"""Agent tools.

Each tool has:
  - a JSON schema (provider-neutral; adapted per provider in llm.py)
  - an implementation that returns {"summary": str, "cards": [..], "suggestions": [..]}

`summary` is the grounded text handed back to the model. `cards` are structured
UI payloads streamed to the frontend (the model never has to serialize them).
`suggestions` are optional follow-up chips.
"""
from typing import Callable, Dict, List

from .catalog import PartsRepository

repo = PartsRepository()


class Cart:
    """Simple in-memory cart. Clears on server restart."""

    def __init__(self):
        self._items: Dict[str, dict] = {}  # ps_number -> {part, quantity}

    def add(self, part: dict, quantity: int = 1) -> dict:
        ps = part["ps_number"]
        if ps in self._items:
            self._items[ps]["quantity"] += quantity
        else:
            self._items[ps] = {"part": part, "quantity": quantity}
        return self._items[ps]

    def remove(self, ps_number: str) -> bool:
        return self._items.pop(ps_number.strip().upper(), None) is not None

    def update_quantity(self, ps_number: str, quantity: int) -> bool:
        key = ps_number.strip().upper()
        if key not in self._items:
            return False
        if quantity <= 0:
            self._items.pop(key)
        else:
            self._items[key]["quantity"] = quantity
        return True

    def clear(self):
        self._items.clear()

    @property
    def items(self) -> List[dict]:
        return list(self._items.values())

    @property
    def total(self) -> float:
        return sum(
            (item["part"].get("price") or 0) * item["quantity"]
            for item in self._items.values()
        )

    @property
    def count(self) -> int:
        return sum(item["quantity"] for item in self._items.values())


cart = Cart()


# --------------------------------------------------------------------------
# Tool schemas (the contract the LLM sees)
# --------------------------------------------------------------------------
TOOL_SCHEMAS = [
    {
        "name": "search_parts",
        "description": (
            "Search the catalog for refrigerator or dishwasher parts by free-text "
            "(e.g. 'door bin', 'ice maker', 'drain pump'). Use when the customer "
            "describes a part but hasn't given a specific part number."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What the customer is looking for."},
                "appliance_type": {
                    "type": "string", "enum": ["Refrigerator", "Dishwasher"],
                    "description": "Filter by appliance type if known.",
                },
                "brand": {"type": "string", "description": "Filter by brand if known (e.g. Whirlpool)."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_part_details",
        "description": (
            "Get full details for one part by its PartSelect number (PS...) or "
            "manufacturer number. Returns price, stock, description, rating, "
            "symptoms it fixes, the list of compatible model numbers, and "
            "replacement part numbers. Use this when the customer asks what "
            "models a part fits or wants general part information."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"part_number": {"type": "string"}},
            "required": ["part_number"],
        },
    },
    {
        "name": "check_compatibility",
        "description": (
            "Check whether a specific part fits a specific appliance model number. "
            "Requires BOTH a part number AND a model number. "
            "Use ONLY when the customer provides a specific model number, e.g. "
            "'is this part compatible with my WDT780SAEM1?'. "
            "Do NOT use this to list compatible models — use get_part_details instead."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "part_number": {"type": "string"},
                "model_number": {"type": "string"},
            },
            "required": ["part_number", "model_number"],
        },
    },
    {
        "name": "get_installation_guide",
        "description": "Get step-by-step installation instructions, tools, difficulty, and time for a part.",
        "input_schema": {
            "type": "object",
            "properties": {"part_number": {"type": "string"}},
            "required": ["part_number"],
        },
    },
    {
        "name": "get_repair_help",
        "description": (
            "Diagnose an appliance symptom and find parts that fix it. "
            "Searches the catalog for parts whose symptoms match the customer's "
            "problem and returns them with descriptions. Use for troubleshooting "
            "questions like 'the ice maker on my fridge isn't working'. "
            "Use the part descriptions to explain the likely cause and fix."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "appliance_type": {"type": "string", "enum": ["Refrigerator", "Dishwasher"]},
                "symptom": {"type": "string", "description": "The problem in the customer's words."},
                "brand": {"type": "string"},
            },
            "required": ["appliance_type", "symptom"],
        },
    },
    {
        "name": "find_parts_for_model",
        "description": "List the parts in our catalog that fit a given appliance model number.",
        "input_schema": {
            "type": "object",
            "properties": {
                "model_number": {"type": "string"},
                "category": {"type": "string", "description": "Optional category filter."},
            },
            "required": ["model_number"],
        },
    },
    {
        "name": "lookup_order",
        "description": "Look up the status of a customer order by order ID (e.g. PS-1042205).",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "email": {"type": "string"},
            },
            "required": ["order_id"],
        },
    },
    {
        "name": "add_to_cart",
        "description": "Add a part to the customer's cart. Returns the updated cart state.",
        "input_schema": {
            "type": "object",
            "properties": {
                "part_number": {"type": "string"},
                "quantity": {"type": "integer", "minimum": 1, "default": 1},
            },
            "required": ["part_number"],
        },
    },
    {
        "name": "view_cart",
        "description": "Show the current contents of the customer's cart with all items and totals.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "remove_from_cart",
        "description": "Remove a part from the cart by its PartSelect number, or clear the entire cart.",
        "input_schema": {
            "type": "object",
            "properties": {
                "part_number": {"type": "string", "description": "PS number to remove. Omit to clear entire cart."},
            },
        },
    },
    {
        "name": "get_symptom_repair_guide",
        "description": (
            "Get a detailed repair guide for a specific appliance symptom. "
            "Use ONLY after get_repair_help returns a symptom list — pick the "
            "symptom URL that best matches the customer's problem and pass it here."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symptom_url": {
                    "type": "string",
                    "description": "The symptom URL from the list returned by get_repair_help.",
                },
            },
            "required": ["symptom_url"],
        },
    },
    {
        "name": "diagnose_model_symptom",
        "description": (
            "Get model-specific diagnosis: which parts fix a symptom on a specific "
            "appliance model, with fix-percentage data. Requires both a model number "
            "and a symptom name. Use after the customer provides their model number "
            "during a repair/troubleshooting conversation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "model_number": {"type": "string"},
                "symptom": {"type": "string", "description": "The symptom to diagnose (e.g. 'Fridge too warm')."},
            },
            "required": ["model_number", "symptom"],
        },
    },
]


# --------------------------------------------------------------------------
# Implementations
# --------------------------------------------------------------------------
def _not_found(part_number):
    return {
        "summary": f"No part matching '{part_number}' was found in the catalog. "
                   f"Ask the customer to double-check the PS number or describe the part.",
        "cards": [],
    }


def tool_search_parts(query, appliance_type=None, brand=None):
    parts = repo.search_parts(query, appliance_type=appliance_type, brand=brand, limit=4)
    if not parts:
        return {"summary": f"No parts matched '{query}'.", "cards": []}
    lines = [f"- {p['name']} (PartSelect #{p['ps_number']}), ${p['price']:.2f}, "
             f"{'in stock' if p['in_stock'] else 'out of stock'}" for p in parts]
    return {
        "summary": f"Found {len(parts)} matching part(s):\n" + "\n".join(lines),
        "cards": [repo.to_product_card(p) for p in parts],
        "suggestions": [f"Does {parts[0]['ps_number']} fit my model?",
                        f"How do I install {parts[0]['ps_number']}?"],
    }


def tool_get_part_details(part_number):
    part = repo.get_part(part_number, enrich=True)
    if not part:
        return _not_found(part_number)
    symptoms = ", ".join(part.get("symptoms_fixed", [])) or "n/a"
    models = part.get("compatible_models", [])
    replaces = part.get("replaces_parts", [])
    lines = [
        f"{part['name']} — PartSelect #{part['ps_number']}, manufacturer "
        f"#{part['mfr_number']}, ${part['price']:.2f}, "
        f"{'in stock' if part['in_stock'] else 'out of stock'}.",
        f"Brand: {part['brand']}. Rating: {part.get('rating') or 'n/a'}/5 "
        f"({part.get('review_count', 0)} reviews).",
        f"Fixes: {symptoms}.",
    ]
    if part.get("description"):
        lines.append(f"Description: {part['description']}")
    if models:
        lines.append(f"Compatible with {len(models)} models including: {', '.join(models[:10])}"
                      + (f" and {len(models) - 10} more." if len(models) > 10 else "."))
    if replaces:
        lines.append(f"Replaces part numbers: {', '.join(replaces)}.")
    summary = "\n".join(lines)
    return {
        "summary": summary,
        "cards": [repo.to_product_card(part)],
        "suggestions": [f"How do I install {part['ps_number']}?",
                        "Is it compatible with my model?",
                        f"Add {part['ps_number']} to my cart"],
    }


def tool_check_compatibility(part_number, model_number):
    res = repo.check_compatibility(part_number, model_number)
    if res.get("status") == "part_not_found":
        return _not_found(part_number)
    part = res["part"]
    card = {
        "type": "compatibility",
        "compatible": res["compatible"],
        "model_number": model_number,
        "model_known": res["model_known"],
        "reason": res["reason"],
        "part": repo.to_product_card(part),
    }
    cards = [card]
    summary = res["reason"]
    if res.get("alternative"):
        alt = res["alternative"]
        card["alternative"] = repo.to_product_card(alt)
        summary += (f" A part that does fit {model_number} is {alt['name']} "
                    f"(PartSelect #{alt['ps_number']}).")
    suggestions = []
    if res["compatible"]:
        suggestions = [f"How do I install {part['ps_number']}?",
                       f"Add {part['ps_number']} to my cart"]
    return {"summary": summary, "cards": cards, "suggestions": suggestions}


def tool_get_installation_guide(part_number):
    part = repo.get_part(part_number, enrich=True)
    if not part:
        return _not_found(part_number)
    install = part.get("install", {})
    tools_list = ", ".join(install.get("tools_required", [])) or "no special tools"
    steps = install.get("steps", [])
    video = install.get("video_url", "")

    lines = [f"Installation info for {part['name']} (#{part['ps_number']}):"]
    if part.get("description"):
        lines.append(f"Part description: {part['description']}")
    if install.get("difficulty"):
        lines.append(f"Difficulty: {install['difficulty']}")
    if install.get("time_estimate"):
        lines.append(f"Estimated time: {install['time_estimate']}")
    lines.append(f"Tools needed: {tools_list}")
    if video:
        lines.append(f"Video guide: {video}")
    if part.get("url"):
        lines.append(f"Full details: {part['url']}")
    if steps:
        lines.append("\nRaw repair notes from customers (summarize these nicely for the user):")
        for i, s in enumerate(steps, 1):
            lines.append(f"  {i}. {s}")

    summary = "\n".join(lines)
    return {"summary": summary, "cards": [],
            "suggestions": [f"Is {part['ps_number']} compatible with my model?",
                            f"Add {part['ps_number']} to my cart"]}


def tool_get_repair_help(appliance_type, symptom, brand=None):
    result = repo.find_repair_help(appliance_type, symptom, brand=brand)

    if result["source"] == "none":
        return {
            "summary": f"No troubleshooting info found for '{symptom}' on a {appliance_type}. "
                       f"Ask the customer for their model number so we can look up "
                       f"compatible parts, or try searching by part name.",
            "cards": [],
        }

    # Live catalog match: parts with symptom data.
    if result["source"] == "live":
        parts = result["parts"]
        lines = [
            f"Troubleshooting '{symptom}' on a {appliance_type}.",
            f"Found {len(parts)} part(s) that may fix this issue:",
        ]
        for p in parts:
            symptoms = ", ".join(p.get("symptoms_fixed", []))
            lines.append(
                f"\n- {p['name']} (#{p['ps_number']}), ${p['price']:.2f}, "
                f"{'in stock' if p['in_stock'] else 'out of stock'}."
            )
            if symptoms:
                lines.append(f"  Fixes: {symptoms}")
            if p.get("description"):
                lines.append(f"  Description: {p['description']}")
        lines.append(
            "\nUse the part descriptions and symptoms to explain to the customer "
            "which part most likely fixes their problem and why. Suggest they "
            "check compatibility with their model number."
        )
        suggestions = [f"Tell me more about {parts[0]['ps_number']}",
                       f"How do I install {parts[0]['ps_number']}?"]
        return {
            "summary": "\n".join(lines),
            "cards": [repo.to_product_card(p) for p in parts],
            "suggestions": suggestions,
        }

    # Live symptom list from PartSelect /Repair/ pages — the LLM picks the
    # best match and calls get_symptom_repair_guide next.
    if result["source"] == "symptom_list":
        symptoms = result["symptoms"]
        lines = [
            f"The customer is reporting '{symptom}' on a {appliance_type}.",
            f"Here are the known symptoms for {appliance_type} repairs:",
        ]
        for s in symptoms:
            lines.append(f"\n- {s['title']}: {s['description'][:150]}")
            lines.append(f"  URL: {s['url']}")
        lines.append(
            "\nPick the symptom that best matches the customer's problem and "
            "call get_symptom_repair_guide with its URL to get the detailed "
            "repair guide with causes and fixes."
        )
        return {"summary": "\n".join(lines), "cards": [], "suggestions": []}

    # Static guide fallback (repair_help.json).
    guide = result["guide"]
    lines = [
        f"Troubleshooting '{guide['symptom']}' on a {appliance_type}.",
        f"Overview: {guide['overview']}",
    ]
    if guide.get("quick_checks"):
        lines.append("\nQuick checks before replacing parts:")
        for check in guide["quick_checks"]:
            lines.append(f"  - {check}")
    lines.append("\nLikely causes (most common first):")
    for cause in guide["causes"]:
        lines.append(f"\n- {cause['title']}: {cause['detail']}")
        for ps in cause.get("recommended_parts", []):
            lines.append(f"  Recommended part: {ps}")
    lines.append(
        "\nExplain the causes to the customer clearly and suggest "
        "which parts they may need to check or replace."
    )
    return {"summary": "\n".join(lines), "cards": [], "suggestions": []}


def tool_find_parts_for_model(model_number, category=None):
    res = repo.parts_for_model(model_number, category=category)
    if res.get("status") == "model_not_found":
        return {
            "summary": f"Model {model_number} isn't in our records. Ask the customer to "
                       f"confirm the model number (it's on a sticker inside the appliance).",
            "cards": [],
        }
    parts = res["parts"]
    model = res["model"]
    summary = (f"{model['brand']} {model['appliance_type']} {model['model_number']}: "
               f"{len(parts)} catalog part(s) available"
               + (f" in category '{category}'" if category else "") + ".")
    return {
        "summary": summary,
        "cards": [repo.to_product_card(p) for p in parts],
        "suggestions": [f"Is PS_____ compatible with {model_number}?".replace("PS_____", parts[0]["ps_number"])]
        if parts else [],
    }


def tool_lookup_order(order_id, email=None):
    order = repo.lookup_order(order_id, email=email)
    if order is None:
        return {
            "summary": f"No order found with ID {order_id}. Ask the customer to confirm "
                       f"the order ID (format PS-1234567).",
            "cards": [],
        }
    if order.get("status") == "email_mismatch":
        return {"summary": "The email provided doesn't match that order. Ask the customer "
                           "to confirm the email used at checkout.", "cards": []}
    card = {"type": "order", **{k: order.get(k) for k in [
        "order_id", "status", "placed_on", "estimated_delivery", "carrier",
        "tracking_number", "tracking_url", "items", "subtotal", "shipping", "total"]}}
    summary = (f"Order {order['order_id']} is '{order['status']}', placed "
               f"{order['placed_on']}, total ${order['total']:.2f}. "
               f"Estimated delivery {order['estimated_delivery']}.")
    return {"summary": summary, "cards": [card], "suggestions": []}


def _cart_card() -> dict:
    """Build a cart card reflecting the full current cart state."""
    items = []
    for entry in cart.items:
        p = entry["part"]
        items.append({
            "ps_number": p["ps_number"],
            "name": p["name"],
            "price": p.get("price") or 0,
            "quantity": entry["quantity"],
            "line_total": round((p.get("price") or 0) * entry["quantity"], 2),
            "image_url": p.get("image_url", ""),
            "url": p.get("url", ""),
        })
    return {
        "type": "cart",
        "items": items,
        "item_count": cart.count,
        "total": round(cart.total, 2),
    }


def tool_add_to_cart(part_number, quantity=1):
    part = repo.get_part(part_number)
    if not part:
        return _not_found(part_number)
    if not part.get("in_stock", True):
        return {"summary": f"{part['name']} (#{part['ps_number']}) is currently out of stock, "
                           f"so it can't be added to the cart.", "cards": []}
    quantity = max(1, int(quantity or 1))
    cart.add(part, quantity)
    summary = (f"Added {quantity} x {part['name']} (#{part['ps_number']}) to the cart. "
               f"Cart now has {cart.count} item(s), total ${cart.total:.2f}.")
    return {"summary": summary, "cards": [_cart_card()],
            "suggestions": [f"How do I install {part['ps_number']}?", "View my cart"]}


def tool_view_cart():
    if not cart.items:
        return {"summary": "The cart is empty.", "cards": [], "suggestions": ["Search for a part"]}
    lines = ["Current cart:"]
    for entry in cart.items:
        p = entry["part"]
        lines.append(f"- {entry['quantity']} x {p['name']} (#{p['ps_number']}), "
                     f"${(p.get('price') or 0) * entry['quantity']:.2f}")
    lines.append(f"\nTotal: ${cart.total:.2f} ({cart.count} item(s))")
    return {"summary": "\n".join(lines), "cards": [_cart_card()], "suggestions": []}


def tool_remove_from_cart(part_number=None):
    if not part_number:
        cart.clear()
        return {"summary": "Cart has been cleared.", "cards": [], "suggestions": ["Search for a part"]}
    key = part_number.strip().upper()
    if cart.remove(key):
        summary = f"Removed {key} from the cart."
        if cart.items:
            summary += f" Cart now has {cart.count} item(s), total ${cart.total:.2f}."
        else:
            summary += " Cart is now empty."
        return {"summary": summary, "cards": [_cart_card()] if cart.items else [],
                "suggestions": []}
    return {"summary": f"{part_number} was not in the cart.", "cards": [],
            "suggestions": ["View my cart"]}


def tool_get_symptom_repair_guide(symptom_url):
    detail = repo.fetch_symptom_repair_guide(symptom_url)
    if not detail:
        return {
            "summary": f"Could not fetch repair guide from {symptom_url}.",
            "cards": [],
        }
    lines = [f"Repair guide: {detail['symptom']}"]
    lines.append("\nLikely causes (most common first):")
    for cause in detail["causes"]:
        lines.append(f"\n- {cause['title']}: {cause['detail']}")
    if detail.get("url"):
        lines.append(f"\nFull guide: {detail['url']}")
    lines.append(
        "\nIMPORTANT: Present ONLY the causes listed above. Do NOT add "
        "causes, tips, or suggestions that are not in this data. "
        "After explaining the causes, ask the customer for their model "
        "number so you can use diagnose_model_symptom to find the exact "
        "parts that fix this issue on their specific appliance."
    )
    return {"summary": "\n".join(lines), "cards": [],
            "suggestions": ["I have my model number"]}


def tool_diagnose_model_symptom(model_number, symptom):
    model_symptoms = repo.fetch_model_symptoms(model_number)
    if not model_symptoms:
        return {
            "summary": f"Could not find symptoms for model {model_number}. "
                       f"The model may not be in PartSelect's database.",
            "cards": [],
        }
    symptom_l = symptom.lower()
    best, best_score = None, 0
    for s in model_symptoms:
        title_l = s["title"].lower()
        score = 0
        if title_l == symptom_l:
            score = 10
        elif title_l in symptom_l or symptom_l in title_l:
            score = 5
        else:
            user_tokens = {t for t in symptom_l.split() if len(t) > 2}
            title_tokens = {t for t in title_l.split() if len(t) > 2}
            score = len(user_tokens & title_tokens) * 2
        if score > best_score:
            best, best_score = s, score
    if not best or best_score < 2:
        syms = ", ".join(s["title"] for s in model_symptoms[:10])
        return {
            "summary": f"Model {model_number} doesn't have a symptom matching "
                       f"'{symptom}'. Available symptoms: {syms}.",
            "cards": [],
        }
    parts_data = repo.fetch_model_symptom_parts(model_number, best["url"])
    if not parts_data:
        return {
            "summary": f"No parts data found for '{best['title']}' on model {model_number}.",
            "cards": [],
        }
    lines = [f"Model-specific diagnosis for {model_number}: {best['title']}",
             f"\nParts that fix this (ranked by likelihood):"]
    for p in parts_data:
        stock = "in stock" if p["in_stock"] else "out of stock"
        price_str = f"${p['price']:.2f}" if p["price"] else "price TBD"
        lines.append(
            f"\n- {p['name']} (#{p['ps_number']}), {price_str}, {stock}"
            f" — fixes this {p['fix_pct']}% of the time"
        )
    lines.append(
        "\nPresent these parts to the customer ranked by fix likelihood. "
        "ONLY mention the parts and percentages listed above."
    )
    # Return product cards so the user gets add-to-cart / view-on-website buttons
    cards = []
    for p in parts_data:
        part_obj = repo.get_part(p["ps_number"])
        if part_obj:
            cards.append(repo.to_product_card(part_obj))
    suggestions = []
    if parts_data:
        top = parts_data[0]
        suggestions = [f"Tell me about {top['ps_number']}",
                       f"Add {top['ps_number']} to cart"]
    return {"summary": "\n".join(lines), "cards": cards, "suggestions": suggestions}


TOOL_IMPLEMENTATIONS: Dict[str, Callable] = {
    "search_parts": tool_search_parts,
    "get_part_details": tool_get_part_details,
    "check_compatibility": tool_check_compatibility,
    "get_installation_guide": tool_get_installation_guide,
    "get_repair_help": tool_get_repair_help,
    "find_parts_for_model": tool_find_parts_for_model,
    "lookup_order": tool_lookup_order,
    "add_to_cart": tool_add_to_cart,
    "view_cart": tool_view_cart,
    "remove_from_cart": tool_remove_from_cart,
    "get_symptom_repair_guide": tool_get_symptom_repair_guide,
    "diagnose_model_symptom": tool_diagnose_model_symptom,
}


def execute_tool(name: str, args: dict) -> dict:
    impl = TOOL_IMPLEMENTATIONS.get(name)
    if not impl:
        return {"summary": f"Unknown tool '{name}'.", "cards": []}
    try:
        return impl(**(args or {}))
    except TypeError as exc:
        return {"summary": f"Tool '{name}' was called with invalid arguments: {exc}.", "cards": []}
    except Exception as exc:  # defensive: never crash the loop on a tool error
        return {"summary": f"Tool '{name}' failed: {exc}.", "cards": []}
